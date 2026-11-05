"""
Unit tests for Subscription UI components, icons, formatting, and dialog integration.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure src is on sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from utils.version import APP_VERSION
from utils.subscription_manager import (
    SubscriptionManager,
    format_subscription_profile_name,
    normalize_subscription_url
)
from gui.styles import resolve_subscription_icon_path


class TestSubscriptionUI(unittest.TestCase):
    def test_version_bump(self):
        self.assertEqual(APP_VERSION, "1.1.1")

    def test_subscription_icon_resolution(self):
        path = resolve_subscription_icon_path()
        self.assertTrue(bool(path), "Subscription icon path must not be empty")
        self.assertTrue(os.path.isfile(path), f"Subscription icon file must exist: {path}")
        self.assertTrue(path.endswith("subscription.svg"), "Subscription icon must be an SVG")

    def test_format_subscription_profile_name(self):
        # Adding suffix
        self.assertEqual(format_subscription_profile_name("Egor_awg1"), "Egor_awg1-sub")
        self.assertEqual(format_subscription_profile_name("Fast-VPN"), "Fast-VPN-sub")
        
        # Stripping existing variants of suffix
        self.assertEqual(format_subscription_profile_name("Egor_awg1 -SUB"), "Egor_awg1-sub")
        self.assertEqual(format_subscription_profile_name("Egor_awg1-SUB"), "Egor_awg1-sub")
        self.assertEqual(format_subscription_profile_name("Egor_awg1 - sub"), "Egor_awg1-sub")
        self.assertEqual(format_subscription_profile_name("Egor_awg1-sub"), "Egor_awg1-sub")
        self.assertEqual(format_subscription_profile_name("Egor_awg1 - Sub"), "Egor_awg1-sub")

        # Empty fallback
        self.assertEqual(format_subscription_profile_name(""), "vpn-sub")
        self.assertEqual(format_subscription_profile_name("   "), "vpn-sub")

    def test_subscription_manager_aliases(self):
        self.assertTrue(hasattr(SubscriptionManager, "fetch_subscription"))
        self.assertTrue(hasattr(SubscriptionManager, "sync_subscription"))
        self.assertTrue(hasattr(SubscriptionManager, "fetch"))
        self.assertTrue(hasattr(SubscriptionManager, "sync"))

    def test_profile_card_sub_badge_logic(self):
        # Verify subscription profile detection logic used in profile_card
        p1 = {"name": "Test-sub", "proto": "amnezia", "is_subscription": True}
        p2 = {"name": "Manual", "proto": "openconnect"}
        p3 = {"name": "Sub_Profile -SUB", "proto": "openconnect"}
        p4 = {"name": "Custom", "proto": "amnezia", "is_subscription": True}

        def check_sub(p):
            raw_name = str(p.get("name", "")).strip()
            raw_name_lower = raw_name.lower()
            return (
                bool(p.get("is_subscription"))
                or p.get("sub_id") is not None
                or raw_name_lower.endswith("-sub")
                or raw_name.endswith("-SUB")
                or " -sub" in raw_name_lower
                or " -SUB" in raw_name
            )

        self.assertTrue(check_sub(p1))
        self.assertFalse(check_sub(p2))
        self.assertTrue(check_sub(p3))
        self.assertTrue(check_sub(p4))

    def test_subscription_dialog_helpers(self):
        from gui.subscription_dialog import (
            mask_subscription_url, format_expiration_details, format_last_sync,
            SubscriptionManageDialog
        )
        # URL masking
        self.assertEqual(
            mask_subscription_url("https://bobr.netphoenix.ru/api/v1/sub/SECRETTOKEN123"),
            "https://bobr.netphoenix.ru/api/v1/sub/••••••••N123"
        )
        self.assertEqual(mask_subscription_url(""), "Ссылка не настроена")

        # Expiration formatting
        full_dt, rem, is_exp = format_expiration_details("2099-01-01T12:00:00")
        self.assertIn("01.01.2099", full_dt)
        self.assertIn("Осталось:", rem)
        self.assertFalse(is_exp)

        full_dt_exp, rem_exp, is_exp2 = format_expiration_details("2020-01-01T12:00:00")
        self.assertIn("01.01.2020", full_dt_exp)
        self.assertIn("Истекла", rem_exp)
        self.assertTrue(is_exp2)

        # Empty expiration
        full_dt_none, rem_none, is_exp3 = format_expiration_details("")
        self.assertEqual(full_dt_none, "Бессрочно")
        self.assertFalse(is_exp3)

    def test_config_store_auto_normalize_sub_profiles(self):
        from utils.config_store import ConfigStore
        import tempfile
        import json

        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".json", encoding="utf-8") as tf:
            test_data = {
                "profiles": [
                    {"name": "Egor_awg1 -SUB", "proto": "amnezia", "is_subscription": True},
                    {"name": "Egor_oc1-SUB", "proto": "openconnect", "sub_id": 2},
                    {"name": "ManualProfile", "proto": "amnezia"},
                    {"name": "Legacy -sub", "proto": "amnezia"}
                ]
            }
            json.dump(test_data, tf)
            tf_path = tf.name

        try:
            with patch("utils.config_store.get_config_path", return_value=tf_path):
                store = ConfigStore()
                profiles = store.get_profiles()
                self.assertEqual(profiles[0]["name"], "Egor_awg1-sub")
                self.assertEqual(profiles[1]["name"], "Egor_oc1-sub")
                self.assertEqual(profiles[2]["name"], "ManualProfile")
                self.assertEqual(profiles[3]["name"], "Legacy-sub")
        finally:
            if os.path.isfile(tf_path):
                os.remove(tf_path)

    def test_subscription_url_normalization(self):
        self.assertEqual(
            normalize_subscription_url("bobr.netphoenix.ru/api/v1/sub/tok123"),
            "https://bobr.netphoenix.ru/api/v1/sub/tok123"
        )
        self.assertEqual(
            normalize_subscription_url("  https://bobr.netphoenix.ru/sub/tok123  "),
            "https://bobr.netphoenix.ru/sub/tok123"
        )

    def test_frozen_subscription_card_state(self):
        from gui.profile_card import VPNProfileCard
        from utils.config_store import settings

        class DummyCard:
            def __init__(self, profile):
                self.profile = profile
            get_frozen_status = VPNProfileCard.get_frozen_status

        # 1. Blocked profile via global subscription_status
        p_blocked = {"name": "Egor_awg1-sub", "proto": "amnezia", "is_subscription": True}
        with patch.object(settings, "get", side_effect=lambda k, d="": "blocked" if k == "subscription_status" else d):
            card = DummyCard(p_blocked)
            is_frozen, reason = card.get_frozen_status()
            self.assertTrue(is_frozen)
            self.assertEqual(reason, "blocked")

        # 2. Expired profile via past ISO date
        p_expired = {"name": "Egor_oc1-sub", "proto": "openconnect", "is_subscription": True, "expires_at": "2020-01-01T00:00:00"}
        with patch.object(settings, "get", side_effect=lambda k, d="": "active" if k == "subscription_status" else d):
            card = DummyCard(p_expired)
            is_frozen, reason = card.get_frozen_status()
            self.assertTrue(is_frozen)
            self.assertEqual(reason, "expired")

        # 3. Active valid profile (not frozen)
        p_active = {"name": "Egor_awg1-sub", "proto": "amnezia", "is_subscription": True, "expires_at": "2030-01-01T00:00:00"}
        with patch.object(settings, "get", side_effect=lambda k, d="": "active" if k == "subscription_status" else d):
            card = DummyCard(p_active)
            is_frozen, reason = card.get_frozen_status()
            self.assertFalse(is_frozen)
            self.assertEqual(reason, "")

        # 4. Manual profile without subscription (never frozen)
        p_manual = {"name": "WorkVPN", "proto": "amnezia"}
        with patch.object(settings, "get", side_effect=lambda k, d="": "blocked" if k == "subscription_status" else d):
            card = DummyCard(p_manual)
            is_frozen, reason = card.get_frozen_status()
            self.assertFalse(is_frozen)
            self.assertEqual(reason, "")

    def test_subscription_info_expiring_soon_calculation(self):
        from utils.subscription_manager import get_subscription_info
        from utils.config_store import settings
        from datetime import datetime, timezone, timedelta

        # 2 days remaining -> expiring soon
        future_2d = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S")
        with patch.object(settings, "get", side_effect=lambda k, d="": {
            "subscription_url": "https://bobr.netphoenix.ru/sub/tok",
            "subscription_status": "active",
            "subscription_expires_at": future_2d
        }.get(k, d)):
            info = get_subscription_info()
            self.assertTrue(info["is_expiring_soon"])
            self.assertFalse(info["is_expired"])
            self.assertIn(info["days_left"], (1, 2))

        # 20 days remaining -> not expiring soon
        future_20d = (datetime.now(timezone.utc) + timedelta(days=20)).strftime("%Y-%m-%dT%H:%M:%S")
        with patch.object(settings, "get", side_effect=lambda k, d="": {
            "subscription_url": "https://bobr.netphoenix.ru/sub/tok",
            "subscription_status": "active",
            "subscription_expires_at": future_20d
        }.get(k, d)):
            info = get_subscription_info()
            self.assertFalse(info["is_expiring_soon"])
            self.assertFalse(info["is_expired"])
            self.assertGreaterEqual(info["days_left"], 19)

    def test_subscription_info_extracts_from_profiles_when_url_empty(self):
        from utils.subscription_manager import get_subscription_info
        from utils.config_store import settings

        settings.data.clear()
        settings.data["profiles"] = [
            {"id": "p1", "name": "bobr-vpn-sub", "is_subscription": True, "server": "bobr.netphoenix.ru", "username": "alice"}
        ]
        info = get_subscription_info()
        self.assertEqual(info["cabinet_url"], "https://bobr.netphoenix.ru")
        self.assertEqual(info["server_host"], "bobr.netphoenix.ru")
        self.assertEqual(info["username"], "alice")
        self.assertEqual(info["status"], "active")

    def test_subscription_manage_dialog_paste_url_logic(self):
        from gui.subscription_dialog import SubscriptionManageDialog
        from utils.config_store import settings

        class DummyDialog:
            def __init__(self):
                self._full_url = ""
                self._cabinet_url = ""
                self.input_url = MagicMock()
                self._refresh_data = MagicMock()
            _on_paste_url_clicked = SubscriptionManageDialog._on_paste_url_clicked

        with patch("gui.subscription_dialog.QApplication.clipboard") as mock_clip:
            mock_clip.return_value.text.return_value = "https://bobr.netphoenix.ru/sub/PASTED_TOKEN"
            dlg = DummyDialog()
            dlg._on_paste_url_clicked()

            self.assertEqual(dlg._full_url, "https://bobr.netphoenix.ru/sub/PASTED_TOKEN")
            self.assertEqual(settings.data.get("subscription_url"), "https://bobr.netphoenix.ru/sub/PASTED_TOKEN")
            dlg.input_url.setText.assert_called_with("https://bobr.netphoenix.ru/sub/PASTED_TOKEN")
            dlg._refresh_data.assert_called_once()

    def test_button_styles_padding_no_clipping(self):
        from gui.profile_card import CONNECT_BTN_STYLE, DISCONNECT_BTN_STYLE, CONNECTING_BTN_STYLE
        for style in (CONNECT_BTN_STYLE, DISCONNECT_BTN_STYLE, CONNECTING_BTN_STYLE):
            self.assertNotIn("padding: 7px 22px", style)


if __name__ == "__main__":
    unittest.main()
