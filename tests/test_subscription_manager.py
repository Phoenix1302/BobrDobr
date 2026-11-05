"""
Unit tests for Subscription Manager and OpenConnectLauncher enhancements.
"""

import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock
import urllib.error
import io

# Add src to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

# Provide mock PySide6 if not installed (for headless test environments)
try:
    import PySide6
except ImportError:
    pyside6 = MagicMock()
    class MockQObject:
        def __init__(self, parent=None):
            pass
    class MockSignal:
        def __init__(self, *args, **kwargs):
            pass
        def emit(self, *args, **kwargs):
            pass
        def connect(self, slot):
            pass
    pyside6.QtCore.QObject = MockQObject
    pyside6.QtCore.Signal = MockSignal
    sys.modules["PySide6"] = pyside6
    sys.modules["PySide6.QtCore"] = pyside6.QtCore
    sys.modules["PySide6.QtWidgets"] = pyside6.QtWidgets
    sys.modules["PySide6.QtGui"] = pyside6.QtGui

from utils.subscription_manager import (
    SubscriptionError,
    normalize_subscription_url,
    format_subscription_profile_name,
    convert_connection_to_profile,
    fetch_subscription,
    sync_subscription,
    get_subscription_info,
    clear_subscription,
    SubscriptionManager,
)
from utils.config_store import settings, GLOBAL_SENSITIVE_KEYS, PROFILE_SECRET_KEYS
from core.openconnect import OpenConnectLauncher


class TestSubscriptionManager(unittest.TestCase):
    def setUp(self):
        # Reset settings memory data for clean tests
        self._orig_profiles = list(settings.get_profiles())
        self._orig_data = dict(settings.data)
        settings.data["profiles"] = []

    def tearDown(self):
        # Restore settings
        settings.data = self._orig_data

    def test_normalize_subscription_url(self):
        self.assertEqual(
            normalize_subscription_url("https://bobr.netphoenix.ru/api/v1/sub/TOKEN123"),
            "https://bobr.netphoenix.ru/api/v1/sub/TOKEN123"
        )
        self.assertEqual(
            normalize_subscription_url("  bobr.netphoenix.ru/sub/TOKEN123  "),
            "https://bobr.netphoenix.ru/sub/TOKEN123"
        )
        with self.assertRaises(SubscriptionError):
            normalize_subscription_url("")

    def test_format_subscription_profile_name(self):
        self.assertEqual(format_subscription_profile_name("Egor_awg1"), "Egor_awg1-sub")
        self.assertEqual(format_subscription_profile_name("Egor_awg1 -SUB"), "Egor_awg1-sub")
        self.assertEqual(format_subscription_profile_name("Egor_awg1-SUB"), "Egor_awg1-sub")
        self.assertEqual(format_subscription_profile_name("Egor_awg1 - sub"), "Egor_awg1-sub")
        self.assertEqual(format_subscription_profile_name("Egor_awg1-sub"), "Egor_awg1-sub")
        self.assertEqual(format_subscription_profile_name("Egor_awg1 - Sub"), "Egor_awg1-sub")
        self.assertEqual(format_subscription_profile_name(""), "vpn-sub")
        self.assertEqual(format_subscription_profile_name("   "), "vpn-sub")

    def test_convert_awg_connection(self):
        conn = {
            "id": 1,
            "proto": "awg",
            "name": "Egor_awg1",
            "mode": "split",
            "ip": "10.8.0.2",
            "ipv6": "fd00:8:0::2",
            "endpoint": "bobr.netphoenix.ru:443",
            "dns": "10.8.0.1",
            "allowed_ips": "0.0.0.0/0, ::/0",
            "obfuscation": {
                "Jc": 4, "Jmin": 40, "Jmax": 70, "S1": 15, "S2": 45,
                "H1": 1, "H2": 2, "H3": 3, "H4": 4
            },
            "config_text": "[Interface]\nPrivateKey = aaaa\nAddress = 10.8.0.2/24\n"
        }
        profile = convert_connection_to_profile(conn)
        self.assertIsNotNone(profile)
        self.assertEqual(profile["name"], "Egor_awg1-sub")
        self.assertEqual(profile["proto"], "amnezia")
        self.assertTrue(profile["is_subscription"])
        self.assertEqual(profile["sub_id"], 1)
        self.assertEqual(profile["config_content"], conn["config_text"])
        self.assertEqual(profile["interface"], "bobr0")
        self.assertEqual(profile["mode"], "split")
        self.assertEqual(profile["address"], "10.8.0.2")

    def test_convert_ocserv_connection(self):
        conn = {
            "id": 2,
            "proto": "ocserv",
            "name": "Egor_oc1",
            "host": "bobr.netphoenix.ru",
            "port": 443,
            "mode": "split",
            "group": "split",
            "username": "Egor_oc1",
            "password": "user_vpn_password",
            "camouflage": {
                "enabled": True,
                "secret": "my_camouflage_token",
                "path": "/my_camouflage_token",
                "connect_url": "https://bobr.netphoenix.ru:443/my_camouflage_token",
                "tls_sni": "bobr.netphoenix.ru",
                "dtls": True
            },
            "uri": "anyconnect://bobr.netphoenix.ru:443/my_camouflage_token?username=Egor_oc1"
        }
        profile = convert_connection_to_profile(conn)
        self.assertIsNotNone(profile)
        self.assertEqual(profile["name"], "Egor_oc1-sub")
        self.assertEqual(profile["proto"], "openconnect")
        self.assertEqual(profile["protocol"], "anyconnect")
        self.assertTrue(profile["is_subscription"])
        self.assertEqual(profile["sub_id"], 2)
        self.assertEqual(profile["server"], "bobr.netphoenix.ru/?my_camouflage_token")
        self.assertEqual(profile["port"], 443)
        self.assertEqual(profile["username"], "Egor_oc1")
        self.assertEqual(profile["password"], "user_vpn_password")
        self.assertEqual(profile["group"], "split")
        self.assertTrue(profile["remember_password"])
        self.assertEqual(profile["camouflage"], "my_camouflage_token")
        self.assertEqual(profile["camouflage_connect_url"], "https://bobr.netphoenix.ru:443/?my_camouflage_token")
        self.assertEqual(profile["camouflage_path"], "/my_camouflage_token")
        self.assertEqual(profile["camouflage_tls_sni"], "bobr.netphoenix.ru")
        self.assertTrue(profile["camouflage_dtls"])
        self.assertEqual(profile["uri"], conn["uri"])

    @patch("urllib.request.urlopen")
    def test_fetch_subscription_success(self, mock_urlopen):
        sample_response = {
            "status": "active",
            "user": {
                "username": "Egor",
                "role": "user",
                "expires_at": "2026-12-04T23:59:59"
            },
            "server": {
                "host": "bobr.netphoenix.ru",
                "app_version": "1.2.1"
            },
            "connections": [
                {"id": 1, "proto": "awg", "name": "Egor_awg1", "config_text": "sample"}
            ]
        }
        mock_resp = MagicMock()
        mock_resp.getcode.return_value = 200
        mock_resp.headers = {"Subscription-Userinfo": "expire=1796428799"}
        mock_resp.read.return_value = json.dumps(sample_response).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        result = fetch_subscription("https://bobr.netphoenix.ru/api/v1/sub/TOKEN")
        self.assertEqual(result["status"], "active")
        self.assertEqual(result["user"]["username"], "Egor")
        self.assertEqual(len(result["connections"]), 1)
        self.assertEqual(result["_expire_timestamp"], 1796428799)

    @patch("urllib.request.urlopen")
    def test_fetch_subscription_errors(self, mock_urlopen):
        # 1. 401 Unauthorized
        err_401 = urllib.error.HTTPError(
            "url", 401, "Unauthorized", {}, io.BytesIO(b'{"error": "Invalid or revoked token"}')
        )
        mock_urlopen.side_effect = err_401
        with self.assertRaises(SubscriptionError) as ctx:
            fetch_subscription("https://bobr.netphoenix.ru/sub/token")
        self.assertIn("Токен подписки недействителен", str(ctx.exception))

        # 2. 403 Blocked
        err_403_blocked = urllib.error.HTTPError(
            "url", 403, "Forbidden", {}, io.BytesIO(b'{"error": "Account is blocked by administrator"}')
        )
        mock_urlopen.side_effect = err_403_blocked
        with self.assertRaises(SubscriptionError) as ctx:
            fetch_subscription("https://bobr.netphoenix.ru/sub/token")
        self.assertIn("Доступ заблокирован администратором", str(ctx.exception))

        # 3. 403 Expired
        err_403_expired = urllib.error.HTTPError(
            "url", 403, "Forbidden", {}, io.BytesIO(b'{"error": "Subscription expired. Please renew access."}')
        )
        mock_urlopen.side_effect = err_403_expired
        with self.assertRaises(SubscriptionError) as ctx:
            fetch_subscription("https://bobr.netphoenix.ru/sub/token")
        self.assertIn("Срок действия подписки истек", str(ctx.exception))

        # 4. Network error
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        with self.assertRaises(SubscriptionError) as ctx:
            fetch_subscription("https://bobr.netphoenix.ru/sub/token")
        self.assertIn("Не удалось подключиться к серверу подписки", str(ctx.exception))

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_fetch_subscription_429_retry(self, mock_urlopen, mock_sleep):
        # 429 fails 3 times then raises
        err_429 = urllib.error.HTTPError(
            "url", 429, "Too Many Requests", {}, io.BytesIO(b'{"error": "Rate limited"}')
        )
        mock_urlopen.side_effect = err_429
        with self.assertRaises(SubscriptionError) as ctx:
            fetch_subscription("https://bobr.netphoenix.ru/sub/token")
        self.assertIn("Превышен лимит запросов к серверу подписок", str(ctx.exception))
        self.assertEqual(mock_sleep.call_count, 3)

    @patch("utils.subscription_manager.fetch_subscription")
    def test_sync_subscription_logic(self, mock_fetch):
        # Setup existing profiles: 1 manual, 1 old subscription profile
        manual_profile = {"id": "man-1", "name": "My Manual Profile", "proto": "amnezia"}
        old_sub_profile = {
            "id": "sub-1-uuid",
            "name": "Egor_awg1 -SUB",
            "proto": "amnezia",
            "is_subscription": True,
            "sub_id": 1
        }
        obsolete_sub_profile = {
            "id": "sub-99-uuid",
            "name": "Removed_sub -SUB",
            "proto": "openconnect",
            "is_subscription": True,
            "sub_id": 99
        }
        settings.data["profiles"] = [manual_profile, old_sub_profile, obsolete_sub_profile]

        server_data = {
            "status": "active",
            "user": {
                "username": "Egor",
                "role": "user",
                "expires_at": "2026-12-04T23:59:59"
            },
            "server": {
                "host": "bobr.netphoenix.ru",
                "app_version": "1.2.1"
            },
            "connections": [
                {
                    "id": 1,
                    "proto": "awg",
                    "name": "Egor_awg1",
                    "config_text": "[Interface]\nAddress = 10.8.0.2/24\n"
                },
                {
                    "id": 2,
                    "proto": "ocserv",
                    "name": "Egor_oc1",
                    "host": "bobr.netphoenix.ru",
                    "port": 443,
                    "username": "Egor_oc1",
                    "password": "pwd"
                }
            ]
        }
        mock_fetch.return_value = server_data

        ok, msg, updated = sync_subscription("https://bobr.netphoenix.ru/api/v1/sub/MYTOKEN")
        self.assertTrue(ok)
        self.assertEqual(len(updated), 2)

        # Check profiles in settings
        all_profiles = settings.get_profiles()
        # manual_profile preserved + 2 sub profiles = 3 total. obsolete_sub_profile pruned!
        self.assertEqual(len(all_profiles), 3)

        # Manual profile intact
        self.assertEqual(all_profiles[0]["id"], "man-1")
        self.assertEqual(all_profiles[0]["name"], "My Manual Profile")

        # Sub profile 1 preserved its original UUID "sub-1-uuid"
        sub1 = next(p for p in all_profiles if p.get("sub_id") == 1)
        self.assertEqual(sub1["id"], "sub-1-uuid")
        self.assertEqual(sub1["name"], "Egor_awg1-sub")

        # Sub profile 2 received a new UUID
        sub2 = next(p for p in all_profiles if p.get("sub_id") == 2)
        self.assertIsNotNone(sub2["id"])
        self.assertNotEqual(sub2["id"], "sub-1-uuid")
        self.assertEqual(sub2["name"], "Egor_oc1-sub")

        # Obsolete sub profile (sub_id 99) is removed
        self.assertIsNone(next((p for p in all_profiles if p.get("sub_id") == 99), None))

        # Check metadata stored in settings
        info = get_subscription_info()
        self.assertEqual(info["url"], "https://bobr.netphoenix.ru/api/v1/sub/MYTOKEN")
        self.assertEqual(info["status"], "active")
        self.assertEqual(info["username"], "Egor")
        self.assertEqual(info["expires_at"], "2026-12-04T23:59:59")
        self.assertEqual(info["server_host"], "bobr.netphoenix.ru")
        self.assertEqual(info["profiles_count"], 2)

    def test_clear_subscription(self):
        manual_profile = {"id": "man-1", "name": "My Manual Profile", "proto": "amnezia"}
        sub_profile = {"id": "sub-1", "name": "Sub -SUB", "proto": "openconnect", "is_subscription": True, "sub_id": 1}
        settings.data["profiles"] = [manual_profile, sub_profile]
        settings.data["subscription_url"] = "https://example.com/sub/tok"
        settings.data["subscription_username"] = "Egor"

        self.assertTrue(clear_subscription())

        all_profiles = settings.get_profiles()
        self.assertEqual(len(all_profiles), 1)
        self.assertEqual(all_profiles[0]["id"], "man-1")
        self.assertNotIn("subscription_url", settings.data)
        self.assertNotIn("subscription_username", settings.data)

    def test_config_store_sensitive_keys(self):
        self.assertIn("subscription_url", GLOBAL_SENSITIVE_KEYS)
        self.assertIn("camouflage_connect_url", PROFILE_SECRET_KEYS)


class TestOpenConnectLauncherUrlHandling(unittest.TestCase):
    def test_openconnect_start_connection_target_parsing(self):
        launcher = OpenConnectLauncher()

        # Mock _spawn_process so no real process is executed
        spawn_mock = MagicMock(return_value=True)
        launcher._spawn_process = spawn_mock
        launcher.error_occurred = MagicMock()

        with patch("core.openconnect.find_binary", return_value="openconnect"):
            # Case 1: connect_url with path and port 443
            launcher.start_connection(
                server="bobr.netphoenix.ru",
                port=443,
                connect_url="https://bobr.netphoenix.ru:443/my_camouflage_token",
                group="split",
                username="test_user",
                password="test_password"
            )
            self.assertTrue(spawn_mock.called)
            cmd = spawn_mock.call_args[1]["cmd"]
            stdin_data = spawn_mock.call_args[1]["stdin_data"]
            self.assertEqual(stdin_data, "test_password")

            # Verify target URL is the last argument and correctly formatted with query string for ocserv
            target = cmd[-1]
            self.assertIn("bobr.netphoenix.ru", target)
            self.assertEqual(target, "https://bobr.netphoenix.ru/?my_camouflage_token")
            # Verify --authgroup is passed
            self.assertIn("--authgroup", cmd)
            group_idx = cmd.index("--authgroup")
            self.assertEqual(cmd[group_idx + 1], "split")

            # Case 2: server with embedded port and path: "bobr.netphoenix.ru:443/my_camouflage_token"
            launcher.start_connection(
                server="bobr.netphoenix.ru:443/my_camouflage_token",
                port=443,
                group="split"
            )
            target = spawn_mock.call_args[1]["cmd"][-1]
            self.assertEqual(target, "https://bobr.netphoenix.ru/?my_camouflage_token")

            # Case 3: server with custom port and path
            launcher.start_connection(
                server="bobr.netphoenix.ru:8443/my_camouflage_token",
                port=8443,
                group="full"
            )
            target = spawn_mock.call_args[1]["cmd"][-1]
            self.assertEqual(target, "https://bobr.netphoenix.ru:8443/?my_camouflage_token")

            # Case 4: camouflage_secret as query
            launcher.start_connection(
                server="bobr.netphoenix.ru",
                port=443,
                camouflage_secret="my_query_secret"
            )
            target = spawn_mock.call_args[1]["cmd"][-1]
            self.assertEqual(target, "https://bobr.netphoenix.ru/?my_query_secret")

            # Case 5: camouflage_secret as path
            launcher.start_connection(
                server="bobr.netphoenix.ru",
                port=443,
                camouflage_secret="/my_path_secret"
            )
            target = spawn_mock.call_args[1]["cmd"][-1]
            self.assertEqual(target, "https://bobr.netphoenix.ru/?my_path_secret")

    def test_429_retry_succeeds_on_second_attempt(self):
        sample_response = {
            "status": "active",
            "user": {"username": "Egor"},
            "connections": []
        }
        err_429 = urllib.error.HTTPError(
            "url", 429, "Too Many Requests", {}, io.BytesIO(b'{"error": "Slow down"}')
        )
        mock_resp = MagicMock()
        mock_resp.getcode.return_value = 200
        mock_resp.headers = {}
        mock_resp.read.return_value = json.dumps(sample_response).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("time.sleep") as mock_sleep:
            with patch("urllib.request.urlopen", side_effect=[err_429, mock_resp]):
                data = fetch_subscription("https://bobr.netphoenix.ru/sub/tok")
                self.assertEqual(data["status"], "active")
                self.assertEqual(mock_sleep.call_count, 1)

    def test_subscription_manager_facade(self):
        self.assertEqual(SubscriptionManager.format_name("test"), "test-sub")
        self.assertTrue(hasattr(SubscriptionManager, "fetch"))
        self.assertTrue(hasattr(SubscriptionManager, "sync"))
        self.assertTrue(hasattr(SubscriptionManager, "get_info"))
        self.assertTrue(hasattr(SubscriptionManager, "clear"))


if __name__ == "__main__":
    unittest.main()
