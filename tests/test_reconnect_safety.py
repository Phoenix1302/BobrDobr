"""
Unit tests for reconnect stability, race condition protection,
console signal safety, and single-instance isolation in BobrDobr VPN.
"""

import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Ensure src/ directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from PySide6.QtCore import QCoreApplication
from core.vpn_manager import VPNLauncherBase, VPNState, send_graceful_windows_signal
from core.openconnect import OpenConnectLauncher
from core.amnezia import AmneziaWGLauncher
from gui.profile_card import VPNProfileCard
from utils.single_instance import UNIFIED_MUTEX_NAME, check_single_instance, release_single_instance

# Ensure QApplication is initialized for Qt signal/slot and GUI operations in headless Wine
from PySide6.QtWidgets import QApplication
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
app = QApplication.instance()
if app is None:
    app = QApplication([])


class DummyLauncher(VPNLauncherBase):
    """Concrete subclass of VPNLauncherBase for lifecycle and concurrency testing."""
    def __init__(self):
        super().__init__(name="DummyVPN")
        self.spawn_called = False

    def start_connection(self, **kwargs) -> bool:
        if self.is_running() or self.state == VPNState.DISCONNECTING:
            self.stop_connection(wait=False)
        self.spawn_called = True
        return True

    def _parse_log_line(self, line: str, channel: str) -> None:
        pass


class TestConsoleSignalSafety(unittest.TestCase):
    """Tests ensuring Windows console control signals never crash the host GUI process."""

    @patch("core.vpn_manager.is_windows", return_value=True)
    def test_send_graceful_windows_signal_never_resets_handler_to_false(self, mock_is_win):
        """
        SetConsoleCtrlHandler(None, False) must NEVER be called, as removing protection
        causes the host Python GUI process to crash with STATUS_CONTROL_C_EXIT.
        """
        mock_k32 = MagicMock()
        mock_k32.AttachConsole.return_value = 1
        mock_k32.GenerateConsoleCtrlEvent.return_value = 1

        with patch("ctypes.windll.kernel32", mock_k32, create=True):
            res = send_graceful_windows_signal(pid=9999)
            self.assertTrue(res)

            # Check all calls made to SetConsoleCtrlHandler
            ctrl_handler_calls = mock_k32.SetConsoleCtrlHandler.call_args_list
            for call in ctrl_handler_calls:
                args = call[0]
                if len(args) >= 2:
                    self.assertNotEqual(
                        args[1], False,
                        "CRITICAL: SetConsoleCtrlHandler was called with False! This strips signal protection."
                    )
            # Ensure SetConsoleCtrlHandler(None, True) was called at least once
            self.assertTrue(any(call[0] == (None, True) for call in ctrl_handler_calls))

    @patch("core.vpn_manager.is_windows", return_value=True)
    def test_send_graceful_windows_signal_skips_dead_process(self, mock_is_win):
        """If the process has already terminated, do not attempt to attach to its console."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0  # Process already exited

        mock_k32 = MagicMock()
        with patch("ctypes.windll.kernel32", mock_k32, create=True):
            res = send_graceful_windows_signal(pid=1234, proc=mock_proc)
            self.assertFalse(res)
            mock_k32.AttachConsole.assert_not_called()

    @patch("core.vpn_manager.is_windows", return_value=True)
    def test_send_graceful_windows_signal_handles_exceptions_gracefully(self, mock_is_win):
        """Any unexpected OS or ctypes exception must be caught and logged safely."""
        mock_k32 = MagicMock()
        mock_k32.AttachConsole.side_effect = RuntimeError("Kernel32 AttachConsole fault")
        with patch("ctypes.windll.kernel32", mock_k32, create=True):
            res = send_graceful_windows_signal(pid=5555)
            self.assertFalse(res)


class TestReconnectRaceConditionSafety(unittest.TestCase):
    """Tests race conditions when disconnecting and reconnecting VPN processes."""

    def test_start_connection_asynchronously_stops_if_already_running(self):
        """
        When start_connection() is called while a process is still running,
        it must asynchronously stop the old process without blocking the UI thread.
        """
        launcher = DummyLauncher()
        old_proc = MagicMock()
        old_proc.poll.return_value = None  # Running
        launcher._process = old_proc
        launcher._state = VPNState.CONNECTED

        with patch.object(launcher, "stop_connection", wraps=launcher.stop_connection) as mock_stop:
            launcher.start_connection()
            mock_stop.assert_called_with(wait=False)
            self.assertTrue(launcher.spawn_called)

    def test_start_connection_asynchronously_stops_if_disconnecting(self):
        """
        When start_connection() is called while launcher is in DISCONNECTING state,
        it must initiate clean asynchronous shutdown without blocking.
        """
        launcher = DummyLauncher()
        launcher._state = VPNState.DISCONNECTING
        old_proc = MagicMock()
        old_proc.poll.return_value = None
        launcher._process = old_proc

        with patch.object(launcher, "stop_connection", wraps=launcher.stop_connection) as mock_stop:
            launcher.start_connection()
            mock_stop.assert_called_with(wait=False)
            self.assertTrue(launcher.spawn_called)

    def test_shutdown_worker_timeout_increased_to_6s(self):
        """Verifies shutdown_worker waits up to 6.0 seconds for graceful teardown."""
        launcher = DummyLauncher()
        old_proc = MagicMock()
        old_proc.pid = 7777
        old_proc.poll.return_value = None
        old_proc.wait.return_value = 0
        launcher._process = old_proc
        launcher._state = VPNState.CONNECTED

        with patch("core.vpn_manager.is_windows", return_value=True), \
             patch("core.vpn_manager.send_graceful_windows_signal", return_value=True):
            launcher.stop_connection(wait=True)
            # Must be called with timeout=6.0
            old_proc.wait.assert_called_with(timeout=6.0)

    def test_shutdown_worker_avoids_taskkill_if_terminated_cleanly(self):
        """Verifies taskkill is NOT invoked when process exits within 6.0s timeout."""
        launcher = DummyLauncher()
        old_proc = MagicMock()
        old_proc.pid = 8888
        old_proc.poll.return_value = None
        old_proc.wait.return_value = 0
        launcher._process = old_proc
        launcher._state = VPNState.CONNECTED

        with patch("core.vpn_manager.is_windows", return_value=True), \
             patch("core.vpn_manager.send_graceful_windows_signal", return_value=True), \
             patch("core.vpn_manager.run_silent_cmd") as mock_cmd:
            launcher.stop_connection(wait=True)
            mock_cmd.assert_not_called()

    def test_shutdown_worker_taskkill_only_if_hung(self):
        """Verifies taskkill is executed ONLY if process remains hung after terminate."""
        import subprocess
        launcher = DummyLauncher()
        old_proc = MagicMock()
        old_proc.pid = 9999
        # poll is None initially and remains None after terminate
        old_proc.poll.return_value = None
        old_proc.wait.side_effect = subprocess.TimeoutExpired(cmd="dummy", timeout=6.0)
        launcher._process = old_proc
        launcher._state = VPNState.CONNECTED

        with patch("core.vpn_manager.is_windows", return_value=True), \
             patch("core.vpn_manager.send_graceful_windows_signal", return_value=True), \
             patch("core.vpn_manager.run_silent_cmd") as mock_cmd:
            launcher.stop_connection(wait=True)
            old_proc.terminate.assert_called_once()
            mock_cmd.assert_called_once_with(["taskkill", "/F", "/T", "/PID", "9999"], timeout=3)

    def test_shutdown_worker_does_not_null_new_process_reference(self):
        """
        If a new connection started while the old one was shutting down in the background,
        the old worker's finally block must NOT overwrite self._process with None!
        """
        launcher = DummyLauncher()
        old_proc = MagicMock()
        old_proc.pid = 1001
        old_proc.poll.return_value = None
        old_proc.wait.return_value = 0

        new_proc = MagicMock()
        new_proc.pid = 2002
        new_proc.poll.return_value = None

        launcher._process = old_proc
        launcher._state = VPNState.CONNECTED

        with patch("core.vpn_manager.send_graceful_windows_signal", return_value=True):
            # Intercept wait to simulate a new process starting during shutdown
            def wait_hook(timeout=None):
                launcher._process = new_proc
                launcher._state = VPNState.CONNECTING
                return 0

            old_proc.wait.side_effect = wait_hook
            launcher.stop_connection(wait=True)

            # Crucial assertion: self._process must NOT be None, it must be new_proc!
            self.assertIs(launcher._process, new_proc)
            self.assertEqual(launcher.state, VPNState.CONNECTING)

    def test_monitor_exit_does_not_null_new_process_reference(self):
        """
        If _monitor_exit fires for an old process after a new process has already been assigned,
        it must not set self._process to None or revert the new state.
        """
        launcher = DummyLauncher()
        old_proc = MagicMock()
        old_proc.wait.return_value = 0

        new_proc = MagicMock()
        new_proc.poll.return_value = None

        launcher._process = new_proc
        launcher._state = VPNState.CONNECTED

        launcher._monitor_exit(old_proc)

        self.assertIs(launcher._process, new_proc)
        self.assertEqual(launcher.state, VPNState.CONNECTED)

    @patch("core.openconnect.is_windows", return_value=True)
    def test_openconnect_cleanup_worker_aborts_if_new_connection_started(self, mock_is_win):
        """
        OpenConnectLauncher.stop_connection's cleanup worker must NOT kill daemons
        if the user has already initiated a new connection or is CONNECTED.
        """
        launcher = OpenConnectLauncher()
        old_proc = MagicMock()
        old_proc.pid = 3001
        old_proc.poll.return_value = 0
        launcher._process = old_proc
        launcher._state = VPNState.CONNECTED

        # Run with mock threading to capture the cleanup_worker target
        cleanup_target = None
        def fake_thread(target=None, daemon=None):
            nonlocal cleanup_target
            cleanup_target = target
            m = MagicMock()
            m.start = MagicMock()
            return m

        with patch("threading.Thread", side_effect=fake_thread), \
             patch("core.openconnect.kill_openconnect_daemons") as mock_kill_daemons, \
             patch("core.vpn_manager.send_graceful_windows_signal", return_value=True):

            # Start stop_connection in non-blocking mode (as during normal UI disconnect)
            launcher.stop_connection(wait=False)
            self.assertIsNotNone(cleanup_target)

            # User immediately clicks connect on another profile -> state becomes CONNECTING
            launcher._state = VPNState.CONNECTING
            launcher._session_run_id += 1

            # When background cleanup_worker executes, it must detect reconnect and abort!
            with patch("time.sleep"):
                cleanup_target()

            mock_kill_daemons.assert_not_called()

    @patch("core.amnezia.is_windows", return_value=True)
    def test_amnezia_cleanup_worker_aborts_if_new_connection_started(self, mock_is_win):
        """
        AmneziaWGLauncher.stop_connection's cleanup worker must NOT kill daemons
        or delete the adapter if a new connection is starting or active.
        """
        launcher = AmneziaWGLauncher()
        old_proc = MagicMock()
        old_proc.pid = 4001
        old_proc.poll.return_value = 0
        launcher._process = old_proc
        launcher._state = VPNState.CONNECTED

        cleanup_target = None
        def fake_thread(target=None, daemon=None):
            nonlocal cleanup_target
            cleanup_target = target
            m = MagicMock()
            m.start = MagicMock()
            return m

        with patch("threading.Thread", side_effect=fake_thread), \
             patch("core.amnezia.kill_amnezia_daemons") as mock_kill_daemons, \
             patch("core.amnezia.delete_wintun_adapter") as mock_del_adapter, \
             patch("core.vpn_manager.send_graceful_windows_signal", return_value=True):

            launcher.stop_connection(wait=False)
            self.assertIsNotNone(cleanup_target)

            # User immediately connects another profile
            launcher._state = VPNState.CONNECTING
            launcher._session_run_id += 1

            with patch("time.sleep"):
                cleanup_target()

            mock_kill_daemons.assert_not_called()
            mock_del_adapter.assert_not_called()


class TestSingleInstanceSafety(unittest.TestCase):
    """Tests single instance mutual exclusion preventing dual install + portable execution."""

    def test_unified_mutex_name(self):
        """Mutex name must be unified to prevent running Installed and Portable concurrently."""
        self.assertEqual(UNIFIED_MUTEX_NAME, "Global\\BobrDobr_VPN_SingleInstance_Unified_v1")

    @patch("utils.single_instance.is_windows", return_value=True)
    def test_check_single_instance_detects_existing_process(self, mock_is_win):
        """If mutex already exists (error 183), check_single_instance must return False."""
        mock_k32 = MagicMock()
        mock_k32.CreateMutexW.return_value = 12345
        mock_k32.GetLastError.return_value = 183  # ERROR_ALREADY_EXISTS

        with patch("ctypes.windll.kernel32", mock_k32, create=True), \
             patch("utils.single_instance.activate_existing_window", return_value=True), \
             patch("utils.single_instance.show_already_running_message"):

            res = check_single_instance(show_dialog=False)
            self.assertFalse(res)


class MockButton:
    def __init__(self, text=""):
        self._text = text
        self._enabled = True
        self._style = ""
        self._obj_name = ""

    def isEnabled(self):
        return self._enabled

    def setEnabled(self, v):
        self._enabled = bool(v)

    def text(self):
        return self._text

    def setText(self, t):
        self._text = str(t)

    def setObjectName(self, n):
        self._obj_name = n

    def setStyleSheet(self, s):
        self._style = s

    def style(self):
        m = MagicMock()
        m.unpolish = MagicMock()
        m.polish = MagicMock()
        return m


class MockCard:
    """Mock representing VPNProfileCard to verify state and button logic without X11 server."""
    def __init__(self, profile):
        self.profile = profile
        self.profile_id = profile.get("id", "test_id")
        self.current_state = VPNState.DISCONNECTED
        self.btn_toggle = MockButton("Подключить")
        self.btn_delete = MockButton("Удалить")
        self.lbl_status = MockButton()
        self.disconnect_requested = MagicMock()
        self.connect_requested = MagicMock()

    get_frozen_status = VPNProfileCard.get_frozen_status
    update_state = VPNProfileCard.update_state
    _on_toggle_clicked = VPNProfileCard._on_toggle_clicked
    _apply_shadow = MagicMock()
    style = MagicMock()
    setProperty = MagicMock()
    setStyleSheet = MagicMock()
    underMouse = MagicMock(return_value=False)

    @property
    def state(self) -> VPNState:
        return self.current_state


class TestProfileCardInterfaceProtection(unittest.TestCase):
    """Tests UI button locking during DISCONNECTING and CONNECTING transitions."""

    def setUp(self):
        self.profile = {
            "id": "test_profile_1",
            "name": "Test Amsterdam",
            "proto": "openconnect",
            "server": "1.2.3.4",
            "port": 443
        }
        self.card = MockCard(self.profile)

    def test_button_disabled_in_disconnecting_state(self):
        """Button must be disabled when state is DISCONNECTING."""
        self.card.update_state(VPNState.CONNECTED)
        self.assertTrue(self.card.btn_toggle.isEnabled())

        self.card.update_state(VPNState.DISCONNECTING)
        self.assertFalse(self.card.btn_toggle.isEnabled())
        self.assertEqual(self.card.btn_toggle.text(), "Отключение...")

    def test_toggle_clicked_ignored_in_disconnecting_state(self):
        """Clicking toggle while DISCONNECTING must do nothing and emit no signals."""
        self.card.update_state(VPNState.DISCONNECTING)

        disconnect_emitted = []
        connect_emitted = []
        self.card.disconnect_requested.emit = lambda pid: disconnect_emitted.append(pid)
        self.card.connect_requested.emit = lambda pid: connect_emitted.append(pid)

        self.card._on_toggle_clicked()

        self.assertEqual(len(disconnect_emitted), 0)
        self.assertEqual(len(connect_emitted), 0)

    def test_button_reenabled_in_disconnected_state(self):
        """Button must be re-enabled when state reaches DISCONNECTED."""
        self.card.update_state(VPNState.DISCONNECTING)
        self.assertFalse(self.card.btn_toggle.isEnabled())

        self.card.update_state(VPNState.DISCONNECTED)
        self.assertTrue(self.card.btn_toggle.isEnabled())
        self.assertEqual(self.card.btn_toggle.text(), "Подключить")

    def test_button_reenabled_in_error_state(self):
        """Button must be re-enabled when state reaches ERROR."""
        self.card.update_state(VPNState.DISCONNECTING)
        self.assertFalse(self.card.btn_toggle.isEnabled())

        self.card.update_state(VPNState.ERROR)
        self.assertTrue(self.card.btn_toggle.isEnabled())

    def test_card_state_property(self):
        """Card must expose state property matching current_state."""
        self.card.update_state(VPNState.CONNECTED)
        self.assertEqual(self.card.state, VPNState.CONNECTED)
        self.card.update_state(VPNState.DISCONNECTING)
        self.assertEqual(self.card.state, VPNState.DISCONNECTING)


if __name__ == "__main__":
    unittest.main()
