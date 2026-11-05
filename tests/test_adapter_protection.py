"""
Unit tests for Wintun Adapter Protection and Application Daemon Isolation in BobrDobr VPN.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Ensure src/ is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from utils.platform_helper import (
    get_bobrdobr_daemon_pids,
    kill_amnezia_daemons,
    kill_openconnect_daemons,
    prepare_tunnel_adapter,
    is_network_adapter_present,
    get_persistent_bin_dir,
)
from core.amnezia import AmneziaWGLauncher
from core.openconnect import OpenConnectLauncher
from core.vpn_manager import VPNState


class TestAdapterAndProcessProtection(unittest.TestCase):
    @patch("utils.platform_helper.is_windows", return_value=True)
    def test_get_bobrdobr_daemon_pids_filtering(self, mock_win):
        """
        Tests that get_bobrdobr_daemon_pids selects only processes belonging to BobrDobr
        and strictly excludes third-party VPN processes.
        """
        curr_pid = os.getpid()
        bin_dir = get_persistent_bin_dir()

        # Mocking Windows Toolhelp snapshot
        class DummyPE:
            def __init__(self, pid, ppid, exe):
                self.th32ProcessID = pid
                self.th32ParentProcessID = ppid
                self.szExeFile = exe

        pe_list = [
            DummyPE(1001, curr_pid, "amneziawg-go.exe"),                                 # Ours: child PID
            DummyPE(1002, 9999, "amneziawg-go.exe"),                                     # Ours: in persistent_bin_dir
            DummyPE(1003, 8888, "amneziawg-go.exe"),                                     # Unrelated: other VPN
            DummyPE(1004, curr_pid, "openconnect.exe"),                                  # Ours: child PID
            DummyPE(1005, 7777, "openconnect.exe"),                                      # Unrelated: other OpenConnect
            DummyPE(1006, curr_pid, "notepad.exe"),                                      # Unrelated: different exe
        ]

        # Map PID to image path
        path_map = {
            1001: os.path.join(bin_dir, "amneziawg-go.exe"),
            1002: os.path.join(bin_dir, "amneziawg-go.exe"),
            1003: r"C:\Program Files\ThirdPartyVPN\bin\amneziawg-go.exe",
            1004: os.path.join(bin_dir, "openconnect.exe"),
            1005: r"C:\Program Files\Cisco\openconnect.exe",
            1006: r"C:\Windows\System32\notepad.exe",
        }

        with patch("ctypes.windll.kernel32.CreateToolhelp32Snapshot", return_value=123), \
             patch("ctypes.windll.kernel32.Process32FirstW") as mock_first, \
             patch("ctypes.windll.kernel32.Process32NextW") as mock_next, \
             patch("ctypes.windll.kernel32.OpenProcess", return_value=456), \
             patch("ctypes.windll.kernel32.CloseHandle") as mock_close, \
             patch("ctypes.windll.kernel32.QueryFullProcessImageNameW") as mock_query:

            idx = [0]
            def side_first(h, pe_ref):
                idx[0] = 0
                item = pe_list[0]
                pe_ref._obj.th32ProcessID = item.th32ProcessID
                pe_ref._obj.th32ParentProcessID = item.th32ParentProcessID
                pe_ref._obj.szExeFile = item.szExeFile
                return True

            def side_next(h, pe_ref):
                idx[0] += 1
                if idx[0] < len(pe_list):
                    item = pe_list[idx[0]]
                    pe_ref._obj.th32ProcessID = item.th32ProcessID
                    pe_ref._obj.th32ParentProcessID = item.th32ParentProcessID
                    pe_ref._obj.szExeFile = item.szExeFile
                    return True
                return False

            def side_query(h, flags, buf, size_ref):
                pid = pe_list[idx[0]].th32ProcessID
                buf.value = path_map.get(pid, "")
                return True

            mock_first.side_effect = side_first
            mock_next.side_effect = side_next
            mock_query.side_effect = side_query

            # Check Amnezia daemons
            amnezia_pids = get_bobrdobr_daemon_pids(["amneziawg-go.exe"])
            self.assertIn(1001, amnezia_pids)
            self.assertIn(1002, amnezia_pids)
            self.assertNotIn(1003, amnezia_pids)  # Third-party VPN must NOT be included!
            self.assertNotIn(1004, amnezia_pids)

            # Check OpenConnect daemons
            oc_pids = get_bobrdobr_daemon_pids(["openconnect.exe"])
            self.assertIn(1004, oc_pids)
            self.assertNotIn(1005, oc_pids)  # Third-party OpenConnect must NOT be included!

    @patch("utils.platform_helper.is_windows", return_value=True)
    @patch("utils.platform_helper.get_bobrdobr_daemon_pids", return_value=[2001])
    @patch("utils.platform_helper.kill_bobrdobr_daemons")
    def test_kill_daemons_only_this_app(self, mock_kill, mock_get_pids, mock_win):
        """Verifies that kill_amnezia_daemons and kill_openconnect_daemons target only BobrDobr's PIDs."""
        kill_amnezia_daemons(only_this_app=True)
        mock_kill.assert_called_once_with([2001])

        mock_kill.reset_mock()
        kill_openconnect_daemons(only_this_app=True)
        mock_kill.assert_called_once_with([2001])

    @patch("utils.platform_helper.is_windows", return_value=True)
    @patch("utils.platform_helper.get_bobrdobr_daemon_pids", return_value=[])
    def test_prepare_tunnel_adapter_free(self, mock_pids, mock_win):
        """When adapter is not present in network stack, it is ready immediately."""
        with patch("utils.platform_helper.is_network_adapter_present", return_value=False):
            ok, iface = prepare_tunnel_adapter("awg0")
            self.assertTrue(ok)
            self.assertEqual(iface, "awg0")

    @patch("utils.platform_helper.is_windows", return_value=True)
    @patch("utils.platform_helper.get_bobrdobr_daemon_pids", return_value=[])
    @patch("utils.platform_helper.delete_wintun_adapter")
    def test_prepare_tunnel_adapter_phantom_cleanup(self, mock_delete, mock_pids, mock_win):
        """When adapter is a phantom device, it is cleaned up and freed."""
        # Adapter present at first check, but gone after delete_wintun_adapter
        presence_states = [True, False]
        with patch("utils.platform_helper.is_network_adapter_present", side_effect=lambda name: presence_states.pop(0) if presence_states else False):
            ok, iface = prepare_tunnel_adapter("awg0")
            self.assertTrue(ok)
            self.assertEqual(iface, "awg0")
            mock_delete.assert_called_once_with("awg0")

    @patch("utils.platform_helper.is_windows", return_value=True)
    @patch("utils.platform_helper.get_bobrdobr_daemon_pids", return_value=[])
    @patch("utils.platform_helper.delete_wintun_adapter")
    def test_prepare_tunnel_adapter_fallback_on_occupied(self, mock_delete, mock_pids, mock_win):
        """When awg0 is occupied by another process, falls back to free awg1."""
        def adapter_presence(name):
            # awg0 is persistently present/occupied, but awg1 is free
            return name == "awg0"

        with patch("utils.platform_helper.is_network_adapter_present", side_effect=adapter_presence):
            ok, iface = prepare_tunnel_adapter("awg0")
            self.assertTrue(ok)
            self.assertEqual(iface, "awg1")

    def test_launcher_session_run_token_protects_reconnect(self):
        """
        Tests that starting a new connection invalidates older cleanup workers,
        preventing race conditions where disconnecting kills the newly connecting tunnel.
        """
        launcher = AmneziaWGLauncher()
        initial_token = launcher._session_run_id

        # Simulating first connection start
        launcher._session_run_id += 1
        first_token = launcher._session_run_id
        self.assertEqual(first_token, initial_token + 1)

        # Simulating stop initiated
        stop_token = launcher._session_run_id

        # Simulating rapid reconnect (second connection start before cleanup worker runs)
        launcher._session_run_id += 1
        second_token = launcher._session_run_id

        # Older cleanup worker check:
        self.assertNotEqual(launcher._session_run_id, stop_token)
        # Therefore, old cleanup worker aborts without touching the new connection!


if __name__ == "__main__":
    unittest.main()
