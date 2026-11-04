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
        self.assertEqual(APP_VERSION, "1.1.0")

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


if __name__ == "__main__":
    unittest.main()
