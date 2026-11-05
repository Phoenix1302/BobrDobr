"""
Unit tests for BobrDobr VPN Subscription Cabinet URL extraction,
personal cabinet button integrations, and browser URL redirection.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Ensure src is in sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from utils.config_store import settings
from utils.subscription_manager import (
    get_cabinet_url,
    fetch_subscription,
    sync_subscription,
    get_subscription_info,
    clear_subscription,
    SubscriptionManager,
)
from gui.subscription_dialog import SubscriptionManageDialog
from gui.profile_card import VPNProfileCard
from main import MainWindow


class TestSubscriptionCabinetURL(unittest.TestCase):
    """Тестирование функции get_cabinet_url на различных форматах ссылок."""

    def setUp(self):
        self._orig_data = dict(settings.data)
        settings.data.clear()

    def tearDown(self):
        settings.data.clear()
        settings.data.update(self._orig_data)

    def test_standard_https_with_path_and_token(self):
        url = "https://persona.netphoenix.ru/api/v1/sub/SECRET_TOKEN_12345"
        self.assertEqual(get_cabinet_url(url), "https://persona.netphoenix.ru")

    def test_subdomain_and_custom_port(self):
        url = "https://cabinet.vpn.netphoenix.ru:8443/sub/v2/my-token"
        self.assertEqual(get_cabinet_url(url), "https://cabinet.vpn.netphoenix.ru:8443")

    def test_http_scheme_and_port(self):
        url = "http://internal-vpn.corp.local:8080/api/sub/TEST"
        self.assertEqual(get_cabinet_url(url), "http://internal-vpn.corp.local:8080")

    def test_url_without_scheme(self):
        url = "persona.netphoenix.ru/api/v1/sub/TOKEN_NO_SCHEME"
        self.assertEqual(get_cabinet_url(url), "https://persona.netphoenix.ru")

    def test_url_without_scheme_with_port(self):
        url = "persona.netphoenix.ru:9443/api/v1/sub/TOKEN_PORT"
        self.assertEqual(get_cabinet_url(url), "https://persona.netphoenix.ru:9443")

    def test_url_with_query_params_and_anchor(self):
        url = "https://persona.netphoenix.ru/api/v1/sub/TOKEN?campaign=summer&lang=ru#instructions"
        self.assertEqual(get_cabinet_url(url), "https://persona.netphoenix.ru")

    def test_url_with_trailing_slashes_and_whitespace(self):
        url = "   https://persona.netphoenix.ru/   "
        self.assertEqual(get_cabinet_url(url), "https://persona.netphoenix.ru")

    def test_empty_and_whitespace_without_settings(self):
        self.assertEqual(get_cabinet_url(""), "")
        self.assertEqual(get_cabinet_url("   "), "")
        self.assertEqual(get_cabinet_url(None), "")

    def test_malformed_url_returns_empty_gracefully(self):
        self.assertEqual(get_cabinet_url("://"), "")
        self.assertEqual(get_cabinet_url(":///no-domain"), "")
        self.assertEqual(get_cabinet_url("invalid url here"), "")

    def test_cache_priority_with_cabinet_url(self):
        settings.data["subscription_cache"] = {
            "cabinet_url": "https://billing.netphoenix.ru/user/cabinet",
            "server": {"host": "persona.netphoenix.ru"}
        }
        settings.data["subscription_url"] = "https://persona.netphoenix.ru/api/v1/sub/TOKEN"
        # When url is empty, cache cabinet_url takes precedence
        self.assertEqual(get_cabinet_url(), "https://billing.netphoenix.ru/user/cabinet")

    def test_cache_priority_with_dashboard_url(self):
        settings.data["subscription_cache"] = {
            "dashboard_url": "https://my-dashboard.vpn.ru",
        }
        settings.data["subscription_url"] = "https://persona.netphoenix.ru/api/v1/sub/TOKEN"
        self.assertEqual(get_cabinet_url(""), "https://my-dashboard.vpn.ru")

    def test_cache_server_nested_cabinet_url(self):
        settings.data["subscription_cache"] = {
            "server": {"cabinet_url": "https://server-cabinet.domain.com"}
        }
        self.assertEqual(get_cabinet_url(""), "https://server-cabinet.domain.com")

    def test_fallback_to_saved_subscription_cabinet_url(self):
        settings.data["subscription_cabinet_url"] = "https://saved-cabinet.domain.com"
        self.assertEqual(get_cabinet_url(), "https://saved-cabinet.domain.com")

    def test_fallback_to_saved_subscription_url_root_domain(self):
        settings.data["subscription_url"] = "https://persona.netphoenix.ru/api/v1/sub/STORED_TOKEN"
        self.assertEqual(get_cabinet_url(), "https://persona.netphoenix.ru")

    def test_subscription_manager_facade_method(self):
        self.assertEqual(
            SubscriptionManager.get_cabinet_url("https://facade.test.com/sub/token"),
            "https://facade.test.com"
        )

    def test_extract_cabinet_url_from_openconnect_subscription_profile(self):
        settings.data["profiles"] = [
            {"id": "p1", "name": "NL-Server-sub", "is_subscription": True, "server": "bobr.netphoenix.ru", "port": 443}
        ]
        self.assertEqual(get_cabinet_url(), "https://bobr.netphoenix.ru")

    def test_extract_cabinet_url_from_amnezia_subscription_profile(self):
        settings.data["profiles"] = [
            {"id": "p2", "name": "DE-Amnezia-sub", "is_subscription": True, "endpoint": "bobr.netphoenix.ru:51820"}
        ]
        self.assertEqual(get_cabinet_url(), "https://bobr.netphoenix.ru")

    def test_extract_cabinet_url_skips_private_ips(self):
        settings.data["profiles"] = [
            {"id": "p3", "name": "Local-sub", "is_subscription": True, "endpoint": "10.0.0.1:51820"}
        ]
        self.assertEqual(get_cabinet_url(), "")


class TestSubscriptionManagerCabinetIntegration(unittest.TestCase):
    """Тестирование сохранения и очистки cabinet_url в жизненном цикле подписки."""

    def setUp(self):
        self._orig_data = dict(settings.data)
        settings.data.clear()

    def tearDown(self):
        settings.data.clear()
        settings.data.update(self._orig_data)

    @patch("urllib.request.urlopen")
    def test_fetch_subscription_extracts_and_saves_cabinet_url(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.getcode.return_value = 200
        mock_resp.headers = {}
        mock_resp.read.return_value = b'{"status": "active", "cabinet_url": "https://cabinet.custom.ru", "connections": []}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = fetch_subscription("https://persona.netphoenix.ru/api/v1/sub/TOKEN")
        self.assertEqual(res.get("cabinet_url"), "https://cabinet.custom.ru")
        self.assertEqual(settings.data.get("subscription_cabinet_url"), "https://cabinet.custom.ru")

    @patch("urllib.request.urlopen")
    def test_fetch_subscription_generates_cabinet_url_if_not_in_body(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.getcode.return_value = 200
        mock_resp.headers = {}
        mock_resp.read.return_value = b'{"status": "active", "connections": []}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = fetch_subscription("https://persona.netphoenix.ru/api/v1/sub/TOKEN")
        self.assertEqual(res.get("cabinet_url"), "https://persona.netphoenix.ru")
        self.assertEqual(settings.data.get("subscription_cabinet_url"), "https://persona.netphoenix.ru")

    def test_get_subscription_info_contains_cabinet_url(self):
        settings.data["subscription_url"] = "https://persona.netphoenix.ru/api/v1/sub/TOKEN"
        info = get_subscription_info()
        self.assertIn("cabinet_url", info)
        self.assertEqual(info["cabinet_url"], "https://persona.netphoenix.ru")

    def test_clear_subscription_removes_cabinet_url(self):
        settings.data["subscription_url"] = "https://persona.netphoenix.ru/api/v1/sub/TOKEN"
        settings.data["subscription_cabinet_url"] = "https://persona.netphoenix.ru"
        self.assertTrue(clear_subscription())
        self.assertNotIn("subscription_cabinet_url", settings.data)
        self.assertNotIn("subscription_url", settings.data)


class TestSubscriptionDialogCabinetButton(unittest.TestCase):
    """Тестирование логики кнопки «Личный кабинет ↗» в диалоге управления подпиской."""

    def setUp(self):
        self._orig_data = dict(settings.data)
        settings.data.clear()

    def tearDown(self):
        settings.data.clear()
        settings.data.update(self._orig_data)

    @patch("gui.subscription_dialog.QLabel")
    def test_dialog_cabinet_button_state_refresh(self, mock_qlabel):
        class DummyDialog:
            def __init__(self):
                self._full_url = ""
                self._cabinet_url = ""
                self.input_url = MagicMock()
                self.btn_cabinet = MagicMock()
                self.lbl_expires = MagicMock()
                self.lbl_user_server = MagicMock()
                self.lbl_last_sync = MagicMock()
                self.lbl_status_badge = MagicMock()
                self.lbl_conn_title = MagicMock()
                self.conn_layout = MagicMock()
                self.conn_layout.count.return_value = 0

            _refresh_data = SubscriptionManageDialog._refresh_data

        settings.data["subscription_url"] = "https://persona.netphoenix.ru/api/v1/sub/TOKEN"
        dlg = DummyDialog()
        dlg._refresh_data()

        self.assertEqual(dlg._cabinet_url, "https://persona.netphoenix.ru")
        dlg.btn_cabinet.setEnabled.assert_called_with(True)

        # Without subscription URL
        settings.data.clear()
        dlg2 = DummyDialog()
        dlg2._refresh_data()
        self.assertEqual(dlg2._cabinet_url, "")
        dlg2.btn_cabinet.setEnabled.assert_called_with(False)

    @patch.object(QDesktopServices, "openUrl")
    def test_dialog_cabinet_button_click_opens_url(self, mock_open_url):
        class DummyDialog:
            _cabinet_url = "https://persona.netphoenix.ru"
            _full_url = "https://persona.netphoenix.ru/api/v1/sub/TOKEN"
            _on_open_cabinet_clicked = SubscriptionManageDialog._on_open_cabinet_clicked

        dlg = DummyDialog()
        dlg._on_open_cabinet_clicked()

        mock_open_url.assert_called_once()
        qurl_arg = mock_open_url.call_args[0][0]
        self.assertEqual(qurl_arg.toString(), "https://persona.netphoenix.ru")

    def test_dialog_url_input_editable_and_text_change_updates_cabinet(self):
        class DummyDialog:
            def __init__(self):
                self._full_url = ""
                self._cabinet_url = ""
                self.input_url = MagicMock()
                self.btn_cabinet = MagicMock()
            _on_url_text_changed = SubscriptionManageDialog._on_url_text_changed

        dlg = DummyDialog()
        dlg._on_url_text_changed("https://bobr.netphoenix.ru/api/v1/sub/NEW_SECRET_TOKEN")
        self.assertEqual(dlg._full_url, "https://bobr.netphoenix.ru/api/v1/sub/NEW_SECRET_TOKEN")
        self.assertEqual(settings.data.get("subscription_url"), "https://bobr.netphoenix.ru/api/v1/sub/NEW_SECRET_TOKEN")
        self.assertEqual(dlg._cabinet_url, "https://bobr.netphoenix.ru")
        dlg.btn_cabinet.setEnabled.assert_called_with(True)


class TestProfileCardCabinetWarning(unittest.TestCase):
    """Тестирование предложения перейти в Личный Кабинет при клике на замороженный профиль."""

    def setUp(self):
        self._orig_data = dict(settings.data)
        settings.data.clear()

    def tearDown(self):
        settings.data.clear()
        settings.data.update(self._orig_data)

    @patch.object(QDesktopServices, "openUrl")
    def test_frozen_profile_click_offers_cabinet_and_opens_on_accept(self, mock_open_url):
        settings.data["subscription_url"] = "https://persona.netphoenix.ru/api/v1/sub/TOKEN"
        settings.data["subscription_status"] = "expired"

        class DummyCard:
            profile = {"id": "test-1", "name": "Server1-sub", "is_subscription": True}
            _show_frozen_warning = VPNProfileCard._show_frozen_warning

        with patch("gui.profile_card.QMessageBox") as MockQMsg:
            mock_inst = MockQMsg.return_value
            buttons_added = []

            def fake_add_button(text, role):
                btn = MagicMock()
                btn.text = text
                buttons_added.append(btn)
                return btn

            mock_inst.addButton.side_effect = fake_add_button
            mock_inst.clickedButton.side_effect = lambda: buttons_added[0]

            card = DummyCard()
            card._show_frozen_warning("expired")

            self.assertGreaterEqual(len(buttons_added), 1)
            mock_open_url.assert_called_once()
            qurl_arg = mock_open_url.call_args[0][0]
            self.assertEqual(qurl_arg.toString(), "https://persona.netphoenix.ru")

    @patch.object(QDesktopServices, "openUrl")
    def test_frozen_profile_without_cabinet_url_does_not_open_browser(self, mock_open_url):
        settings.data["subscription_status"] = "blocked"

        class DummyCard:
            profile = {"id": "test-2", "name": "Server2-sub", "is_subscription": True}
            _show_frozen_warning = VPNProfileCard._show_frozen_warning

        with patch("gui.profile_card.QMessageBox") as MockQMsg:
            mock_inst = MockQMsg.return_value
            buttons_added = []

            def fake_add_button(text, role):
                btn = MagicMock()
                btn.text = text
                buttons_added.append(btn)
                return btn

            mock_inst.addButton.side_effect = fake_add_button
            mock_inst.clickedButton.side_effect = lambda: buttons_added[0] if buttons_added else None

            card = DummyCard()
            card._show_frozen_warning("blocked")

            mock_open_url.assert_not_called()


class TestMainWindowCabinetButtons(unittest.TestCase):
    """Тестирование кнопок Личного Кабинета в шапке (Header) и информационном баннере."""

    def setUp(self):
        self._orig_data = dict(settings.data)
        settings.data.clear()

    def tearDown(self):
        settings.data.clear()
        settings.data.update(self._orig_data)

    def test_header_cabinet_button_visibility(self):
        class DummyMainWindow:
            def __init__(self):
                self.btn_subscription = MagicMock()
                self.btn_cabinet = MagicMock()
                self.announcement_banner = MagicMock()
                self.btn_banner_cabinet = MagicMock()
                self.btn_banner_action = MagicMock()
                self.lbl_banner_icon = MagicMock()
                self.lbl_banner_text = MagicMock()
                self._banner_dismissed = False

            _update_subscription_ui = MainWindow._update_subscription_ui
            _update_subscription_banner = MainWindow._update_subscription_banner

        win = DummyMainWindow()

        # Initially no subscription -> hidden
        win._update_subscription_ui()
        win.btn_cabinet.setVisible.assert_called_with(False)

        # Set subscription URL -> visible
        settings.data["subscription_url"] = "https://persona.netphoenix.ru/api/v1/sub/TOKEN"
        win._update_subscription_ui()
        win.btn_cabinet.setVisible.assert_called_with(True)

    @patch.object(QDesktopServices, "openUrl")
    def test_header_cabinet_button_click_opens_url(self, mock_open_url):
        settings.data["subscription_url"] = "https://persona.netphoenix.ru/api/v1/sub/TOKEN"

        class DummyMainWindow:
            _on_open_cabinet_clicked = MainWindow._on_open_cabinet_clicked

        win = DummyMainWindow()
        win._on_open_cabinet_clicked()

        mock_open_url.assert_called_once()
        qurl_arg = mock_open_url.call_args[0][0]
        self.assertEqual(qurl_arg.toString(), "https://persona.netphoenix.ru")

    def test_banner_cabinet_button_states(self):
        class DummyMainWindow:
            def __init__(self):
                self.announcement_banner = MagicMock()
                self.btn_banner_cabinet = MagicMock()
                self.btn_banner_action = MagicMock()
                self.lbl_banner_icon = MagicMock()
                self.lbl_banner_text = MagicMock()
                self._banner_dismissed = False

            _update_subscription_banner = MainWindow._update_subscription_banner

        win = DummyMainWindow()

        # Case 1: Subscription expired -> "Продлить в личном кабинете ↗"
        settings.data["subscription_url"] = "https://persona.netphoenix.ru/api/v1/sub/TOKEN"
        settings.data["subscription_status"] = "expired"
        win._update_subscription_banner()

        win.announcement_banner.setVisible.assert_called_with(True)
        win.btn_banner_cabinet.setVisible.assert_called_with(True)
        win.btn_banner_cabinet.setText.assert_called_with("Продлить в личном кабинете ↗")

        # Case 2: Subscription blocked -> "Открыть личный кабинет ↗"
        settings.data["subscription_status"] = "blocked"
        win._update_subscription_banner()

        win.announcement_banner.setVisible.assert_called_with(True)
        win.btn_banner_cabinet.setVisible.assert_called_with(True)
        win.btn_banner_cabinet.setText.assert_called_with("Открыть личный кабинет ↗")

        # Case 3: Subscription active and not expiring -> banner hidden
        settings.data["subscription_status"] = "active"
        settings.data["subscription_expires_at"] = "2099-01-01T00:00:00"
        win._update_subscription_banner()

        win.announcement_banner.setVisible.assert_called_with(False)
        win.btn_banner_cabinet.setVisible.assert_called_with(False)


if __name__ == "__main__":
    unittest.main()
