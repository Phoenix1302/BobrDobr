"""
Unit tests for Single Instance Unified Mutex and Settings Atomic Protection in BobrDobr VPN.
"""

import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock

# Ensure src/ is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from utils.single_instance import (
    UNIFIED_MUTEX_NAME,
    LEGACY_INSTALLED_MUTEX,
    LEGACY_PORTABLE_MUTEX,
    check_single_instance,
    release_single_instance,
    activate_existing_window,
    show_already_running_message,
)
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

    def test_activate_existing_window_ipc(self):
        """Tests that activate_existing_window connects to QLocalServer and delivers activation request."""
        from PySide6.QtCore import QCoreApplication
        from PySide6.QtNetwork import QLocalServer

        app = QCoreApplication.instance()
        if app is None:
            app = QCoreApplication(sys.argv)

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


if __name__ == "__main__":
    unittest.main()
