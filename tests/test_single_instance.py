"""
Unit tests for Single Instance Unified Mutex and Settings Atomic Protection in BobrDobr VPN.
"""

import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock

# Ensure headless offscreen platform for Qt tests
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Ensure src/ is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from PySide6.QtWidgets import QApplication
if QApplication.instance() is None:
    _global_test_app = QApplication(sys.argv)

from utils.single_instance import (
    UNIFIED_MUTEX_NAME,
    LEGACY_INSTALLED_MUTEX,
    LEGACY_PORTABLE_MUTEX,
    check_single_instance,
    release_single_instance,
    activate_existing_window,
    show_already_running_message,
    _create_mutex_security_attributes,
    try_acquire_single_instance,
    find_other_bobrdobr_processes,
    is_process_alive,
    terminate_bobrdobr_process,
    terminate_all_bobrdobr_processes,
    terminate_orphaned_vpn_daemons,
    handle_startup_single_instance,
)
from gui.instance_dialog import InstanceConflictDialog
from utils.config_store import ConfigStore


class TestSingleInstanceUnified(unittest.TestCase):
    def tearDown(self):
        release_single_instance()

    def test_unified_mutex_name(self):
        """Verifies that the unified mutex name matches the required specification."""
        self.assertEqual(UNIFIED_MUTEX_NAME, "Global\\BobrDobr_VPN_SingleInstance_Unified_v1")

    def test_single_instance_acquisition_and_collision(self):
        """
        Tests that first instance succeeds, second duplicate instance is blocked,
        and release_single_instance allows re-acquisition.
        """
        # Ensure fresh state
        release_single_instance()

        with patch("utils.single_instance.activate_existing_window") as mock_activate, \
             patch("utils.single_instance.show_already_running_message") as mock_msg:

            # 1. First instance acquires mutex successfully
            first_run = check_single_instance(show_dialog=True)
            self.assertTrue(first_run)
            mock_activate.assert_not_called()
            mock_msg.assert_not_called()

            # 2. Duplicate instance is blocked
            second_run = check_single_instance(show_dialog=True)
            self.assertFalse(second_run)
            mock_activate.assert_called_once()
            mock_msg.assert_called_once()

            # 3. Release mutex
            release_single_instance()

            # 4. Re-acquisition succeeds
            third_run = check_single_instance(show_dialog=True)
            self.assertTrue(third_run)

    def test_access_denied_treated_as_duplicate(self):
        """
        Tests that when CreateMutexW fails with ERROR_ACCESS_DENIED (5)
        (e.g., standard user running while administrator holds mutex),
        it is recognized as an active instance, activates window, and returns False.
        """
        release_single_instance()

        import ctypes
        kernel32 = ctypes.windll.kernel32
        ERROR_ACCESS_DENIED = 5

        with patch("utils.single_instance.activate_existing_window") as mock_activate, \
             patch("utils.single_instance.show_already_running_message") as mock_msg, \
             patch.object(kernel32, "CreateMutexW", return_value=0), \
             patch.object(kernel32, "GetLastError", return_value=ERROR_ACCESS_DENIED):

            result = check_single_instance(show_dialog=True)
            self.assertFalse(result)
            mock_activate.assert_called_once()
            mock_msg.assert_called_once()

    def test_already_exists_treated_as_duplicate(self):
        """
        Tests that when CreateMutexW returns ERROR_ALREADY_EXISTS (183),
        it closes the duplicate handle and returns False.
        """
        release_single_instance()

        import ctypes
        kernel32 = ctypes.windll.kernel32
        ERROR_ALREADY_EXISTS = 183
        dummy_handle = 9999

        with patch("utils.single_instance.activate_existing_window") as mock_activate, \
             patch("utils.single_instance.show_already_running_message") as mock_msg, \
             patch.object(kernel32, "CreateMutexW", return_value=dummy_handle), \
             patch.object(kernel32, "GetLastError", return_value=ERROR_ALREADY_EXISTS), \
             patch.object(kernel32, "CloseHandle") as mock_close:

            result = check_single_instance(show_dialog=False)
            self.assertFalse(result)
            mock_activate.assert_called_once()
            mock_msg.assert_not_called()
            mock_close.assert_called_with(dummy_handle)

    def test_legacy_mutex_detection(self):
        """
        Tests that if an older version holds the legacy mutex, the unified check
        detects it as an active instance and returns False.
        """
        release_single_instance()

        import ctypes
        kernel32 = ctypes.windll.kernel32
        # Simulate an older installed or portable version holding legacy mutex
        h_legacy = kernel32.CreateMutexW(None, False, LEGACY_INSTALLED_MUTEX)
        try:
            with patch("utils.single_instance.activate_existing_window") as mock_activate, \
                 patch("utils.single_instance.show_already_running_message") as mock_msg:
                # With show_dialog=False
                is_single = check_single_instance(show_dialog=False)
                self.assertFalse(is_single)
                mock_activate.assert_called_once()
                mock_msg.assert_not_called()
        finally:
            if h_legacy:
                kernel32.CloseHandle(h_legacy)
            release_single_instance()

    def test_legacy_mutex_access_denied_detection(self):
        """
        Tests that if opening a legacy mutex fails with ERROR_ACCESS_DENIED,
        it is recognized as an active instance and returns False.
        """
        release_single_instance()

        import ctypes
        kernel32 = ctypes.windll.kernel32
        ERROR_ACCESS_DENIED = 5

        with patch("utils.single_instance.activate_existing_window") as mock_activate, \
             patch.object(kernel32, "CreateMutexW", return_value=1234), \
             patch.object(kernel32, "OpenMutexW", return_value=0), \
             patch.object(kernel32, "GetLastError", side_effect=[0, ERROR_ACCESS_DENIED]):

            is_single = check_single_instance(show_dialog=False)
            self.assertFalse(is_single)
            mock_activate.assert_called_once()

    def test_security_attributes_sddl_creation(self):
        """Tests that _create_mutex_security_attributes produces valid SA struct with SDDL."""
        sa, cleanup = _create_mutex_security_attributes()
        self.assertIsNotNone(sa)
        self.assertIsNotNone(sa.lpSecurityDescriptor)
        self.assertEqual(sa.bInheritHandle, False)
        if cleanup:
            cleanup()

    def test_security_attributes_fallback_to_null_dacl(self):
        """Tests that if SDDL conversion fails, fallback to InitializeSecurityDescriptor + NULL DACL succeeds."""
        import ctypes
        advapi32 = ctypes.windll.advapi32
        with patch.object(advapi32, "ConvertStringSecurityDescriptorToSecurityDescriptorW", return_value=0):
            sa, cleanup = _create_mutex_security_attributes()
            self.assertIsNotNone(sa)
            self.assertIsNotNone(sa.lpSecurityDescriptor)
            if cleanup:
                cleanup()

    def test_activate_existing_window_fallback_broadcast(self):
        """Tests that activate_existing_window falls back to AllowSetForegroundWindow and WM_BOBRDOBR_ACTIVATE broadcast."""
        import ctypes
        user32 = ctypes.windll.user32
        with patch.object(user32, "AllowSetForegroundWindow") as mock_asfw, \
             patch.object(user32, "PostMessageW") as mock_pm, \
             patch.object(user32, "EnumWindows") as mock_ew:

            res = activate_existing_window()
            self.assertFalse(res)
            mock_asfw.assert_any_call(0xFFFFFFFF)
            self.assertTrue(mock_pm.called)
            self.assertTrue(mock_ew.called)

    def test_activate_existing_window_ipc(self):
        """Tests that activate_existing_window connects to QLocalServer and delivers activation request."""
        from PySide6.QtWidgets import QApplication
        from PySide6.QtNetwork import QLocalServer

        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)

        server = QLocalServer()
        server.removeServer("BobrDobr_VPN_SingleInstance_IPC")
        self.assertTrue(server.listen("BobrDobr_VPN_SingleInstance_IPC"))

        connection_received = []

        def on_conn():
            client = server.nextPendingConnection()
            if client:
                connection_received.append(True)

        server.newConnection.connect(on_conn)

        try:
            res = activate_existing_window()
            # Allow event loop to process
            app.processEvents()
            self.assertTrue(len(connection_received) > 0)
        finally:
            server.close()
            server.removeServer("BobrDobr_VPN_SingleInstance_IPC")


class TestConfigAtomicSaveAndRecovery(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.temp_dir = tempfile.mkdtemp(prefix="bobr_test_cfg_")
        self.config_path = os.path.join(self.temp_dir, "settings.json")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("utils.config_store.get_config_path")
    def test_atomic_save_and_backup_creation(self, mock_path):
        mock_path.return_value = self.config_path

        store = ConfigStore()
        store.data["test_key"] = "initial_val"
        store.save()

        # Primary file created
        self.assertTrue(os.path.isfile(self.config_path))
        with open(self.config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data.get("test_key"), "initial_val")

        # Second save creates .bak with initial_val
        store.data["test_key"] = "updated_val"
        store.save()

        bak_path = f"{self.config_path}.bak"
        self.assertTrue(os.path.isfile(bak_path))
        with open(bak_path, "r", encoding="utf-8") as f:
            bak_data = json.load(f)
        self.assertEqual(bak_data.get("test_key"), "initial_val")

        with open(self.config_path, "r", encoding="utf-8") as f:
            curr_data = json.load(f)
        self.assertEqual(curr_data.get("test_key"), "updated_val")

    @patch("utils.config_store.get_config_path")
    def test_recovery_from_backup_on_corruption(self, mock_path):
        mock_path.return_value = self.config_path

        store = ConfigStore()
        store.save_profile({"id": "prof1", "proto": "amnezia", "name": "Protected Profile"})

        # Make a second save with an updated setting so .bak is created with the good profile
        store.data["extra"] = "backup_checkpoint"
        store.save()

        # Simulate catastrophic disk corruption / 0-byte file on primary
        with open(self.config_path, "w", encoding="utf-8") as f:
            f.write("CORRUPTED_JSON_DATA{[[")

        # Now load new store; it should seamlessly recover from .bak
        recovered_store = ConfigStore()
        prof = recovered_store.get_profile("prof1")
        self.assertIsNotNone(prof)
        self.assertEqual(prof.get("name"), "Protected Profile")


class TestProcessManagerAndTermination(unittest.TestCase):
    """Tests for process discovery, alive check, and cross-integrity termination."""

    def test_is_process_alive_with_current_pid(self):
        """Current process PID must be recognized as alive."""
        self.assertTrue(is_process_alive(os.getpid()))
        self.assertFalse(is_process_alive(-1))
        self.assertFalse(is_process_alive(0))

    @patch("subprocess.run")
    @patch("utils.single_instance.is_process_alive")
    def test_terminate_bobrdobr_process_standard(self, mock_alive, mock_run):
        """Tests that standard taskkill is invoked and succeeds when process dies."""
        # Process alive initially and after IPC, then dies after taskkill
        mock_alive.side_effect = [True, True, False, False, False, False]
        mock_run.return_value = MagicMock(returncode=0)

        res = terminate_bobrdobr_process(pid=12345, timeout_sec=1.0)
        self.assertTrue(res)
        all_calls = [c[0][0] for c in mock_run.call_args_list if c[0] and isinstance(c[0][0], list)]
        self.assertTrue(any("12345" in cmd for cmd in all_calls))

    @patch("ctypes.windll.shell32.ShellExecuteW")
    @patch("subprocess.run")
    @patch("utils.single_instance.is_process_alive")
    def test_terminate_bobrdobr_process_uac_escalation(self, mock_alive, mock_run, mock_shellexec):
        """
        Tests that when standard taskkill fails to kill an elevated process,
        ShellExecuteW is invoked with 'runas' to escalate via Windows UAC.
        """
        mock_run.return_value = MagicMock(returncode=1)  # Access Denied
        mock_shellexec.return_value = 42  # Success > 32

        # Process stays alive through IPC and standard taskkill, dies after UAC ShellExecuteW
        def alive_side_effect(p):
            return not mock_shellexec.called
        mock_alive.side_effect = alive_side_effect

        res = terminate_bobrdobr_process(pid=99999, timeout_sec=1.0)
        self.assertTrue(res)
        mock_shellexec.assert_called_once_with(
            None,
            "runas",
            "taskkill.exe",
            "/F /T /PID 99999",
            None,
            0
        )

    def test_instance_conflict_dialog_creation(self):
        """Verifies that InstanceConflictDialog constructs cleanly in both active and ghost modes."""
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)

        # Ghost mode
        dlg_ghost = InstanceConflictDialog(
            proc_info={"pid": 1111, "mode": "Портативная версия"},
            is_ghost=True
        )
        self.assertIn("фоновый", dlg_ghost.windowTitle().lower())
        dlg_ghost.close()

        # Active mode
        dlg_active = InstanceConflictDialog(
            proc_info={"pid": 2222, "mode": "Установленная версия"},
            is_ghost=False
        )
        self.assertIn("уже запущен", dlg_active.windowTitle().lower())
        dlg_active.close()


class TestInteractiveInstanceStartup(unittest.TestCase):
    """Tests startup conflict resolution flows in handle_startup_single_instance."""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def tearDown(self):
        release_single_instance()

    @patch("utils.single_instance.try_acquire_single_instance")
    def test_startup_clean_run(self, mock_acquire):
        """When mutex is free, handle_startup_single_instance returns True immediately."""
        mock_acquire.return_value = True
        res = handle_startup_single_instance(self.app)
        self.assertTrue(res)

    @patch("utils.single_instance.find_other_bobrdobr_processes")
    @patch("gui.instance_dialog.InstanceConflictDialog")
    @patch("utils.single_instance.activate_existing_window")
    @patch("utils.single_instance.terminate_all_bobrdobr_processes")
    @patch("utils.single_instance.try_acquire_single_instance")
    def test_startup_collision_user_terminates_other(
        self, mock_acquire, mock_terminate, mock_activate, mock_dlg_class, mock_find
    ):
        """
        When collision occurs and user clicks 'Завершить другой экземпляр',
        the other instance is terminated, mutex re-acquired, and startup returns True.
        """
        from PySide6.QtWidgets import QDialog
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.Accepted
        mock_dlg_class.return_value = mock_dlg

        mock_find.return_value = [{"pid": 12345, "mode": "Портативная версия"}]
        # First acquire fails (collision), second acquire after termination succeeds
        mock_acquire.side_effect = [False, True]
        mock_activate.return_value = True
        mock_terminate.return_value = True

        res = handle_startup_single_instance(self.app)
        self.assertTrue(res)
        mock_terminate.assert_called_once()

    @patch("gui.instance_dialog.InstanceConflictDialog")
    @patch("utils.single_instance.activate_existing_window")
    @patch("utils.single_instance.try_acquire_single_instance")
    def test_startup_collision_user_cancels(self, mock_acquire, mock_activate, mock_dlg_class):
        """When user clicks 'Оставить активное окно' or Cancel, startup returns False."""
        from PySide6.QtWidgets import QDialog
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.Rejected
        mock_dlg_class.return_value = mock_dlg

        mock_acquire.return_value = False
        mock_activate.return_value = True

        res = handle_startup_single_instance(self.app)
        self.assertFalse(res)


if __name__ == "__main__":
    unittest.main()
