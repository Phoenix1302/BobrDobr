import sys
import os
import time
from typing import Dict, Optional

# Ensure src/ directory is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QMessageBox, QFrame, QScrollArea, QPushButton, QDialog,
    QSystemTrayIcon, QMenu, QAbstractButton, QRadioButton, QCheckBox,
    QGraphicsDropShadowEffect, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, QSize, QObject, QEvent
from PySide6.QtGui import QIcon, QPixmap, QPainter, QPalette, QColor
from PySide6.QtSvg import QSvgRenderer

from core.vpn_manager import VPNState
from core.amnezia import AmneziaWGLauncher
from core.openconnect import OpenConnectLauncher
from gui.styles import DARK_THEME_QSS, get_stylesheet
from gui.profile_card import VPNProfileCard
from gui.profile_dialog import ProfileDialog, PasswordPromptDialog
from gui.log_viewer import LogViewer
from gui.installer_dialog import InstallDialog, UninstallDialog, UpdateDialog, GitHubUpdateDialog
from utils.platform_helper import is_windows, is_admin, get_base_dir, ensure_persistent_binaries, init_windows_job_object
from utils.installer_helper import is_installed_mode, has_installed_version
from utils.version import APP_VERSION, APP_TITLE, GITHUB_REPO, GITHUB_RELEASES_URL
from utils.config_store import settings
from utils.github_updater import GitHubUpdateCheckerThread


class MainWindow(QMainWindow):
    """
    Главное окно приложения БобрДобр VPN.
    Единый список подключений (AmneziaWG и OpenConnect) с возможностью
    добавления, редактирования и удаления профилей с сохранением в settings.json.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)

        # Привязываем процесс к Windows Job Object (гарантия автозавершения amneziawg-go при выходе)
        if is_windows():
            init_windows_job_object()

        # Извлекаем бинарники в постоянный каталог и настраиваем Windows Firewall
        ensure_persistent_binaries()

        # Восстановление геометрии
        saved_w = settings.get("window_width", 840)
        saved_h = settings.get("window_height", 820)
        try:
            w = max(int(saved_w), 840)
            h = max(int(saved_h), 780)
        except (ValueError, TypeError):
            w, h = 840, 820
        self.resize(w, h)
        self.setMinimumSize(780, 620)

        # Иконка окна и трея
        self.beaver_icon_path = self._resolve_icon_path()
        self.beaver_ico_path = self._resolve_ico_path()
        self.log_svg_path = self._resolve_log_svg_path()
        if os.path.exists(self.beaver_ico_path):
            self.app_icon = QIcon(self.beaver_ico_path)
        elif os.path.exists(self.beaver_icon_path):
            self.app_icon = QIcon(self.beaver_icon_path)
        else:
            self.app_icon = QIcon()

        if not self.app_icon.isNull():
            self.setWindowIcon(self.app_icon)

        # Трей и управление завершением
        self._force_quitting = False
        self._init_tray_icon()

        # Ядро оркестрации
        self.amnezia_launcher = AmneziaWGLauncher(self)
        self.openconnect_launcher = OpenConnectLauncher(self)

        # Активное подключение
        self.active_profile_id: Optional[str] = None
        self.cards: Dict[str, VPNProfileCard] = {}

        # Таймер
        self._connected_start_time: float = 0.0
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._update_timer_label)

        # Автоматическая фоновая проверка обновлений на GitHub (через 3.5 секунды)
        self._update_checker_thread: Optional[GitHubUpdateCheckerThread] = None
        self._latest_update_info: Optional[dict] = None
        QTimer.singleShot(3500, self._start_silent_update_check)

        self._init_ui()
        self._wire_signals()
        self._render_profiles()

    def _resolve_icon_path(self) -> str:
        candidates = [
            os.path.join(get_base_dir(), "assets", "beaver.svg"),
            os.path.join(get_base_dir(), "src", "assets", "beaver.svg"),
            os.path.join(os.path.dirname(__file__), "assets", "beaver.svg"),
        ]
        for c in candidates:
            if os.path.isfile(c):
                return os.path.abspath(c)
        return ""

    def _resolve_ico_path(self) -> str:
        candidates = [
            os.path.join(get_base_dir(), "assets", "beaver.ico"),
            os.path.join(get_base_dir(), "src", "assets", "beaver.ico"),
            os.path.join(os.path.dirname(__file__), "assets", "beaver.ico"),
        ]
        for c in candidates:
            if os.path.isfile(c):
                return os.path.abspath(c)
        return ""

    def _resolve_log_svg_path(self) -> str:
        candidates = [
            os.path.join(get_base_dir(), "assets", "log.svg"),
            os.path.join(get_base_dir(), "src", "assets", "log.svg"),
            os.path.join(os.path.dirname(__file__), "assets", "log.svg"),
        ]
        for c in candidates:
            if os.path.isfile(c):
                return os.path.abspath(c)
        return ""

    def _init_tray_icon(self):
        """Initializes system tray icon with context menu and click handlers."""
        self.tray_icon = QSystemTrayIcon(self.app_icon, self)
        self.tray_icon.setToolTip(APP_TITLE)

        self.tray_menu = QMenu(self)
        self.tray_menu.setObjectName("tray_menu")
        self.tray_menu.aboutToShow.connect(self._on_tray_menu_about_to_show)
        self.tray_menu.aboutToHide.connect(self._on_tray_menu_about_to_hide)

        self.action_show_hide = self.tray_menu.addAction("🖥  Показать окно")
        self.action_show_hide.triggered.connect(self._toggle_window_visibility)

        self.tray_menu.addSeparator()

        self.action_tray_status = self.tray_menu.addAction("⚪  Плотина не активна")
        self.action_tray_status.setEnabled(False)

        self.action_tray_disconnect = self.tray_menu.addAction("🔌  Отключить VPN")
        self.action_tray_disconnect.setEnabled(False)
        self.action_tray_disconnect.triggered.connect(self._tray_disconnect_vpn)

        self.tray_menu.addSeparator()

        self.action_tray_update = self.tray_menu.addAction("🚀  Доступна новая версия!")
        self.action_tray_update.setVisible(False)
        self.action_tray_update.triggered.connect(self._on_update_available_clicked)

        self.action_tray_check_updates = self.tray_menu.addAction("🔄  Проверить обновления...")
        self.action_tray_check_updates.triggered.connect(self._check_updates_interactive)

        self.tray_menu.addSeparator()

        action_quit = self.tray_menu.addAction("🚪  Выход из БобрДобр")
        action_quit.triggered.connect(self._tray_force_quit)

        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _on_tray_menu_about_to_show(self):
        if self.isVisible() and not self.isMinimized():
            self.action_show_hide.setText("👁  Скрыть окно")
        else:
            self.action_show_hide.setText("🖥  Показать окно")

        if is_windows():
            try:
                import ctypes
                user32 = ctypes.windll.user32
                h_overflow = user32.FindWindowW("NotifyIconOverflowWindow", None)
                if h_overflow and user32.IsWindowVisible(h_overflow):
                    # Привязываем меню как дочернее к панели переполнения трея, чтобы панель не уезжала
                    menu_hwnd = int(self.tray_menu.winId())
                    set_long = getattr(user32, "SetWindowLongPtrW", None) or getattr(user32, "SetWindowLongW", None)
                    if set_long:
                        set_long(menu_hwnd, -8, h_overflow)  # GWLP_HWNDPARENT = -8
                user32.SetForegroundWindow(int(self.tray_menu.winId()))
            except Exception:
                pass

    def _on_tray_menu_about_to_hide(self):
        if is_windows():
            try:
                import ctypes
                user32 = ctypes.windll.user32
                set_long = getattr(user32, "SetWindowLongPtrW", None) or getattr(user32, "SetWindowLongW", None)
                if set_long:
                    set_long(int(self.tray_menu.winId()), -8, 0)
            except Exception:
                pass

    def _toggle_window_visibility(self):
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            self.showNormal()
            self.activateWindow()
            self.raise_()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._toggle_window_visibility()

    def _tray_disconnect_vpn(self):
        if self.active_profile_id:
            self._on_disconnect_profile(self.active_profile_id)
        else:
            if self.amnezia_launcher.is_running():
                self.amnezia_launcher.stop_connection()
            if self.openconnect_launcher.is_running():
                self.openconnect_launcher.stop_connection()

    def _tray_force_quit(self):
        """Cleanly and forcefully disconnects all VPNs and closes the application."""
        self._force_quitting = True
        self._clean_shutdown(wait=True)
        if hasattr(self, "tray_icon"):
            self.tray_icon.hide()
        self.close()
        QApplication.instance().quit()
        try:
            import os
            os._exit(0)
        except Exception:
            sys.exit(0)

    def _clean_shutdown(self, wait: bool = True):
        if hasattr(self, "amnezia_launcher") and self.amnezia_launcher.is_running():
            self.amnezia_launcher.stop_connection(wait=wait)
        if hasattr(self, "openconnect_launcher") and self.openconnect_launcher.is_running():
            self.openconnect_launcher.stop_connection(wait=wait)

    def _update_tray_state(self, state: VPNState, vpn_name: str):
        if not hasattr(self, "tray_icon"):
            return
        if state == VPNState.CONNECTED:
            p = settings.get_profile(self.active_profile_id)
            p_name = p.get("name", vpn_name) if p else vpn_name
            self.tray_icon.setToolTip(f"БобрДобр: Подключено ({p_name})")
            self.action_tray_status.setText(f"🟢  Подключено: {p_name}")
            self.action_tray_disconnect.setEnabled(True)
        elif state == VPNState.CONNECTING:
            self.tray_icon.setToolTip("БобрДобр: Подключение...")
            self.action_tray_status.setText("🟡  Подключение к плотине...")
            self.action_tray_disconnect.setEnabled(True)
        elif state == VPNState.DISCONNECTING:
            self.tray_icon.setToolTip("БобрДобр: Отключение...")
            self.action_tray_status.setText("🟡  Отключение...")
            self.action_tray_disconnect.setEnabled(False)
        else:
            self.tray_icon.setToolTip(APP_TITLE)
            self.action_tray_status.setText("⚪  Плотина не активна")
            self.action_tray_disconnect.setEnabled(False)

    def _update_installer_button(self):
        if is_installed_mode():
            self.btn_installer.setObjectName("btn_installed_badge")
            self.btn_installer.setText("⚙ Установлен на ПК")
            self.btn_installer.setToolTip("БобрДобр установлен в систему. Нажмите для управления, перевода в Portable или удаления.")
        elif has_installed_version():
            self.btn_installer.setObjectName("btn_install_badge")
            self.btn_installer.setText("🔄 Обновить на ПК")
            self.btn_installer.setToolTip("На этом ПК обнаружена установленная версия БобрДобр. Нажмите для чистой установки и обновления с сохранением всех подключений.")
        else:
            self.btn_installer.setObjectName("btn_install_badge")
            self.btn_installer.setText("+ Установить на ПК")
            self.btn_installer.setToolTip("Установить БобрДобр на компьютер (создать ярлыки на Рабочем столе и в меню «Пуск»)")
        self.btn_installer.style().unpolish(self.btn_installer)
        self.btn_installer.style().polish(self.btn_installer)

    def _on_installer_clicked(self):
        if is_installed_mode():
            dlg = UninstallDialog(self, self.app_icon)
            if dlg.exec() == QDialog.Accepted:
                if dlg.selected_action in ("uninstall", "portable"):
                    self._tray_force_quit()
        else:
            if is_windows() and not is_admin():
                action_text = "обновления программы на ПК" if has_installed_version() else "установки БобрДобр на ПК и создания системных ярлыков"
                msg = QMessageBox(self)
                msg.setWindowTitle("Требуются права администратора")
                msg.setText(
                    f"Для {action_text} требуются права администратора.\n\n"
                    "Повысить статус до Старшего гидроинженера?"
                )
                msg.setIcon(QMessageBox.Question)
                btn_elevate = msg.addButton("Повысить статус", QMessageBox.YesRole)
                btn_elevate.setObjectName("btn_primary")
                btn_elevate.setCursor(Qt.PointingHandCursor)
                btn_cancel = msg.addButton("Отмена", QMessageBox.NoRole)
                btn_cancel.setObjectName("btn_secondary")
                btn_cancel.setCursor(Qt.PointingHandCursor)
                msg.setDefaultButton(btn_elevate)
                msg.exec()
                if msg.clickedButton() == btn_elevate:
                    self._elevate_and_restart()
                return

            if has_installed_version():
                dlg = UpdateDialog(self, self.app_icon)
            else:
                dlg = InstallDialog(self, self.app_icon)

            if dlg.exec() == QDialog.Accepted:
                self._update_installer_button()
                self._render_profiles()

    def _prompt_admin_elevation(self):
        """Easter egg / interactive prompt to promote user to Admin."""
        msg = QMessageBox(self)
        msg.setWindowTitle("Повышение статуса бобрёнка")
        msg.setText(
            "Вы запустили БобрДобр в режиме «Младший бобрёнок».\n\n"
            "Для возведения сетевых плотин (создания адаптера Wintun и настройки системных маршрутов) "
            "требуются повышенные привилегии.\n\n"
            "Повысить статус до Старшего гидроинженера?"
        )
        msg.setIcon(QMessageBox.Question)
        btn_elevate = msg.addButton("Повысить статус", QMessageBox.YesRole)
        btn_elevate.setObjectName("btn_primary")
        btn_elevate.setCursor(Qt.PointingHandCursor)
        btn_cancel = msg.addButton("Остаться младшим", QMessageBox.NoRole)
        btn_cancel.setObjectName("btn_secondary")
        btn_cancel.setCursor(Qt.PointingHandCursor)
        msg.setDefaultButton(btn_elevate)
        msg.exec()
        if msg.clickedButton() == btn_elevate:
            self._elevate_and_restart()

    def _elevate_and_restart(self):
        """Re-launches the current process using Windows 'runas' UAC verb."""
        import ctypes
        try:
            exe = sys.executable
            if getattr(sys, "frozen", False):
                args = " ".join([f'"{a}"' for a in sys.argv[1:]])
            else:
                args = " ".join([f'"{a}"' for a in sys.argv])
            ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, args, None, 1)
            if ret > 32:
                self._tray_force_quit()
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось перезапустить с повышением прав:\n{e}")

    def _init_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 16, 20, 14)
        main_layout.setSpacing(12)

        # 1. Хедер (Брендинг + Статус админа)
        header_layout = QHBoxLayout()
        logo_layout = QHBoxLayout()
        logo_layout.setSpacing(10)

        logo_label = QLabel()
        if os.path.isfile(self.beaver_icon_path):
            renderer = QSvgRenderer(self.beaver_icon_path)
            pixmap = QPixmap(36, 36)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            logo_label.setPixmap(pixmap)
        logo_layout.addWidget(logo_label)

        brand_text_layout = QVBoxLayout()
        brand_text_layout.setSpacing(2)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_row.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        title_label = QLabel("БобрДобр")
        title_label.setStyleSheet("font-size: 22px; font-weight: 800; color: #d97706; letter-spacing: -0.5px;")
        title_row.addWidget(title_label)

        self.ver_badge = QLabel(f"v{APP_VERSION}")
        self.ver_badge.setStyleSheet(
            "color: #94a3b8; font-size: 11px; font-weight: 700; "
            "background-color: #1a252a; border: 1px solid #283941; "
            "border-radius: 6px; padding: 2px 7px;"
        )
        self.ver_badge.setCursor(Qt.PointingHandCursor)
        self.ver_badge.setToolTip("Нажмите, чтобы проверить обновления на GitHub")
        self.ver_badge.mousePressEvent = lambda e: self._check_updates_interactive()
        title_row.addWidget(self.ver_badge)

        self.btn_update_available = QPushButton("🚀 Обновление")
        self.btn_update_available.setCursor(Qt.PointingHandCursor)
        self.btn_update_available.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #d97706, stop:1 #b45309);
                color: #ffffff;
                font-size: 11px;
                font-weight: 800;
                border: 1px solid #f59e0b;
                border-radius: 6px;
                padding: 2px 9px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f59e0b, stop:1 #d97706);
            }
        """)
        self.btn_update_available.setToolTip("Нажмите для просмотра релиза и загрузки новой версии")
        self.btn_update_available.clicked.connect(self._on_update_available_clicked)
        self.btn_update_available.setVisible(False)
        title_row.addWidget(self.btn_update_available)

        brand_text_layout.addLayout(title_row)

        subtitle_label = QLabel("Центр гидробиологических инноваций | Сетевая плотина")
        subtitle_label.setStyleSheet("font-size: 11px; color: #94a3b8; font-weight: 600;")
        brand_text_layout.addWidget(subtitle_label)

        logo_layout.addLayout(brand_text_layout)
        header_layout.addLayout(logo_layout)
        header_layout.addStretch()

        # Кнопка установки / удаления из системы
        self.btn_installer = QPushButton()
        self.btn_installer.setCursor(Qt.PointingHandCursor)
        self._update_installer_button()
        self.btn_installer.clicked.connect(self._on_installer_clicked)
        header_layout.addWidget(self.btn_installer)

        # Бейдж прав администратора
        admin_status = is_admin()
        admin_text = "● Старший гидроинженер" if admin_status else "○ Младший бобрёнок"
        admin_color = "#34d399" if admin_status else "#fbbf24"
        admin_bg = "rgba(16, 185, 129, 0.12)" if admin_status else "rgba(217, 119, 6, 0.12)"
        admin_border = "rgba(16, 185, 129, 0.35)" if admin_status else "rgba(217, 119, 6, 0.35)"

        self.lbl_admin = QLabel(admin_text)
        self.lbl_admin.setStyleSheet(
            f"color: {admin_color}; background-color: {admin_bg}; "
            f"border: 1px solid {admin_border}; border-radius: 14px; padding: 5px 14px; font-size: 11px; font-weight: 700;"
        )
        if not admin_status:
            self.lbl_admin.setCursor(Qt.PointingHandCursor)
            self.lbl_admin.setToolTip("Нажмите, чтобы повысить статус до Старшего гидроинженера")
            self.lbl_admin.mousePressEvent = lambda e: self._prompt_admin_elevation()
        header_layout.addWidget(self.lbl_admin)
        main_layout.addLayout(header_layout)

        # 2. Панель действий со списком подключений
        action_bar = QHBoxLayout()
        action_bar.setSpacing(10)

        title_sec = QLabel("Мои VPN подключения")
        title_sec.setStyleSheet("font-size: 17px; font-weight: 800; color: #f8fafc;")
        action_bar.addWidget(title_sec)

        self.lbl_count_badge = QLabel("0")
        self.lbl_count_badge.setStyleSheet("""
            background-color: rgba(217, 119, 6, 0.12);
            color: #f59e0b;
            font-size: 11px;
            font-weight: 800;
            border: 1px solid rgba(217, 119, 6, 0.30);
            border-radius: 10px;
            padding: 2px 9px;
        """)
        action_bar.addWidget(self.lbl_count_badge)

        action_bar.addStretch()

        # Кнопка добавления подключения
        btn_add = QPushButton("+ Создать подключение")
        btn_add.setObjectName("btn_primary")
        btn_add.setCursor(Qt.PointingHandCursor)
        btn_add.clicked.connect(self._on_add_profile)
        action_bar.addWidget(btn_add)

        main_layout.addLayout(action_bar)

        # 3. Единый скроллируемый список карточек (все в одной колонке)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll_area.viewport().setStyleSheet("background: transparent;")

        self.profiles_container = QWidget()
        self.profiles_container.setStyleSheet("background: transparent;")
        self.profiles_layout = QVBoxLayout(self.profiles_container)
        self.profiles_layout.setContentsMargins(10, 8, 10, 8)
        self.profiles_layout.setSpacing(14)

        scroll_area.setWidget(self.profiles_container)
        main_layout.addWidget(scroll_area, stretch=1)

        # 4. Нижняя статусная панель и сворачиваемый журнал
        bottom_frame = QFrame()
        bottom_frame.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #141c22, stop:1 #0c1215);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-top: 1px solid rgba(255, 255, 255, 0.16);
            border-radius: 12px;
        """)
        bottom_shadow = QGraphicsDropShadowEffect(bottom_frame)
        bottom_shadow.setXOffset(0)
        bottom_shadow.setYOffset(3)
        bottom_shadow.setBlurRadius(16)
        bottom_shadow.setColor(QColor(0, 0, 0, 110))
        bottom_frame.setGraphicsEffect(bottom_shadow)

        bottom_layout = QVBoxLayout(bottom_frame)
        bottom_layout.setContentsMargins(14, 10, 14, 10)
        bottom_layout.setSpacing(8)

        status_bar_layout = QHBoxLayout()
        status_bar_layout.setSpacing(12)

        self.status_pill = QLabel("○ Плотина не построена")
        self.status_pill.setObjectName("status_pill")
        self._update_status_pill_style(VPNState.DISCONNECTED.value)
        status_bar_layout.addWidget(self.status_pill)

        self.lbl_active_proto = QLabel("Речной трафик идёт открыто")
        self.lbl_active_proto.setStyleSheet("color: #94a3b8; font-size: 12px; margin-left: 2px;")
        status_bar_layout.addWidget(self.lbl_active_proto)

        status_bar_layout.addStretch()

        self.lbl_timer = QLabel("00:00:00")
        self.lbl_timer.setStyleSheet("""
            background-color: rgba(217, 119, 6, 0.10);
            color: #f59e0b;
            border: 1px solid rgba(217, 119, 6, 0.25);
            border-radius: 8px;
            padding: 4px 12px;
            font-family: 'Cascadia Code', Consolas, monospace;
            font-size: 13px;
            font-weight: 800;
        """)
        status_bar_layout.addWidget(self.lbl_timer)

        # Кнопка сворачивания/разворачивания лога
        self.btn_toggle_log = QPushButton("📋 Журнал событий ▼")
        self.btn_toggle_log.setObjectName("btn_toggle_log")
        self.btn_toggle_log.setCursor(Qt.PointingHandCursor)
        self.btn_toggle_log.clicked.connect(self._toggle_log_viewer)
        status_bar_layout.addWidget(self.btn_toggle_log)

        bottom_layout.addLayout(status_bar_layout)

        # Бортовой журнал (по умолчанию свёрнут)
        self.log_viewer = LogViewer()
        self.log_viewer.setVisible(False)
        bottom_layout.addWidget(self.log_viewer)

        main_layout.addWidget(bottom_frame)

        # Футер
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(0, 4, 0, 0)
        footer_layout.setAlignment(Qt.AlignCenter)
        footer_layout.setSpacing(10)

        footer_label = QLabel(f"© 2026 БобрДобр v{APP_VERSION} | Все бобры накормлены. Протечки устранены.")
        footer_label.setStyleSheet("color: #475569; font-size: 11px; font-weight: 500;")
        footer_layout.addWidget(footer_label)

        btn_check_upd = QPushButton("Проверить обновления")
        btn_check_upd.setCursor(Qt.PointingHandCursor)
        btn_check_upd.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #64748b;
                font-size: 11px;
                text-decoration: underline;
                font-weight: 600;
                padding: 0px 4px;
            }
            QPushButton:hover {
                color: #f59e0b;
            }
        """)
        btn_check_upd.clicked.connect(self._check_updates_interactive)
        footer_layout.addWidget(btn_check_upd)

        main_layout.addLayout(footer_layout)

    def _render_profiles(self):
        """Очищает и заново отображает все карточки из settings.json в одной колонке."""
        # Очистка текущих элементов
        while self.profiles_layout.count():
            item = self.profiles_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self.cards.clear()
        profiles = settings.get_profiles()
        self.lbl_count_badge.setText(str(len(profiles)))

        if not profiles:
            empty_card = QFrame()
            empty_card.setObjectName("empty_card")
            empty_card.setStyleSheet("""
                QFrame#empty_card {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #18232a, stop:1 #0f161a);
                    border: 1px dashed rgba(255, 255, 255, 0.16);
                    border-radius: 12px;
                }
                QFrame#empty_card QLabel {
                    border: none;
                    background: transparent;
                    padding: 0px;
                }
            """)
            empty_card.setMinimumHeight(240)
            empty_layout = QVBoxLayout(empty_card)
            empty_layout.setContentsMargins(24, 28, 24, 28)
            empty_layout.setSpacing(10)
            empty_layout.setAlignment(Qt.AlignCenter)

            lbl_empty_icon = QLabel()
            lbl_empty_icon.setStyleSheet("border: none; background: transparent; margin-bottom: 2px;")
            lbl_empty_icon.setAlignment(Qt.AlignCenter)
            log_path = getattr(self, "log_svg_path", "") or self._resolve_log_svg_path()
            if os.path.isfile(log_path):
                renderer = QSvgRenderer(log_path)
                pixmap = QPixmap(64, 64)
                pixmap.fill(Qt.transparent)
                painter = QPainter(pixmap)
                renderer.render(painter)
                painter.end()
                lbl_empty_icon.setPixmap(pixmap)
            empty_layout.addWidget(lbl_empty_icon)

            lbl_empty = QLabel("Плотины ещё не возведены")
            lbl_empty.setStyleSheet("font-size: 16px; font-weight: bold; color: #cbd5e1; border: none; background: transparent;")
            lbl_empty.setAlignment(Qt.AlignCenter)
            empty_layout.addWidget(lbl_empty)

            lbl_empty_sub = QLabel("Нажмите «+ Создать подключение», чтобы добавить конфигурацию AmneziaWG или шлюз OpenConnect.")
            lbl_empty_sub.setWordWrap(True)
            lbl_empty_sub.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            lbl_empty_sub.setMinimumHeight(44)
            lbl_empty_sub.setStyleSheet("font-size: 12px; color: #94a3b8; line-height: 1.4; border: none; background: transparent;")
            lbl_empty_sub.setAlignment(Qt.AlignCenter)
            empty_layout.addWidget(lbl_empty_sub)

            self.profiles_layout.addWidget(empty_card)
        else:
            for p in profiles:
                p_id = p.get("id")
                card = VPNProfileCard(p)
                card.connect_requested.connect(self._on_connect_profile)
                card.disconnect_requested.connect(self._on_disconnect_profile)
                card.edit_requested.connect(self._on_edit_profile)
                card.delete_requested.connect(self._on_delete_profile)

                if self.active_profile_id == p_id:
                    # Восстанавливаем статус активного
                    active_launcher = self.amnezia_launcher if p.get("proto") == "amnezia" else self.openconnect_launcher
                    card.update_state(active_launcher.state)

                self.cards[p_id] = card
                self.profiles_layout.addWidget(card)

        self.profiles_layout.addStretch()

    def _toggle_log_viewer(self):
        new_state = not self.log_viewer.isVisible()
        self.log_viewer.setVisible(new_state)
        arrow = "▲" if new_state else "▼"
        self.btn_toggle_log.setText(f"📋 Журнал событий {arrow}")

    def _on_add_profile(self):
        dlg = ProfileDialog(parent=self)
        if dlg.exec() == QDialog.Accepted:
            new_data = dlg.get_data()
            settings.save_profile(new_data)
            self._render_profiles()

    def _on_edit_profile(self, profile_id: str):
        prof = settings.get_profile(profile_id)
        if not prof:
            return
        dlg = ProfileDialog(profile=dict(prof), parent=self)
        if dlg.exec() == QDialog.Accepted:
            updated = dlg.get_data()
            settings.save_profile(updated)
            self._render_profiles()

    def _on_delete_profile(self, profile_id: str):
        prof = settings.get_profile(profile_id)
        if not prof:
            return

        name = prof.get("name", "это подключение")
        msg = QMessageBox(self)
        msg.setWindowTitle("Удаление подключения")
        msg.setText(f"Вы действительно хотите разобрать плотину «{name}» и удалить это подключение?")
        msg.setIcon(QMessageBox.Question)
        btn_del = msg.addButton("Да, удалить", QMessageBox.YesRole)
        btn_del.setStyleSheet("background-color: #b91c1c; color: #ffffff;")
        btn_cancel = msg.addButton("Отмена", QMessageBox.NoRole)
        msg.setDefaultButton(btn_cancel)
        msg.exec()
        if msg.clickedButton() == btn_del:
            if self.active_profile_id == profile_id:
                self._on_disconnect_profile(profile_id, wait=True)
            settings.delete_profile(profile_id)
            self._render_profiles()

    def _on_connect_profile(self, profile_id: str):
        if is_windows() and not is_admin():
            self._prompt_admin_elevation()
            return

        profile = settings.get_profile(profile_id)
        if not profile:
            return

        # Если активно другое подключение — инициируем мгновенную визуальную индикацию переключения
        if self.active_profile_id and self.active_profile_id != profile_id:
            old_id = self.active_profile_id

            # 1. Моментальное жёлтое/янтарное состояние на новой карточке
            if profile_id in self.cards:
                self.cards[profile_id].update_state(
                    VPNState.CONNECTING,
                    custom_status="⏳ Переподключение...",
                    custom_btn="Переподключение..."
                )

            # 2. Моментальное жёлтое состояние на старой карточке
            if old_id in self.cards:
                self.cards[old_id].update_state(
                    VPNState.DISCONNECTING,
                    custom_status="⏳ Отключение...",
                    custom_btn="Отключение..."
                )

            # 3. Моментальный жёлтый статус-бар внизу
            self.status_pill.setText("● Переподключение...")
            self.status_pill.setStyleSheet(
                "background-color: #451a03; color: #fbbf24; border: 1px solid #d97706; "
                "border-radius: 12px; padding: 4px 14px; font-weight: 800; font-size: 11px;"
            )
            p_name = profile.get("name", "VPN")
            self.lbl_active_proto.setText(f"Переключение на «{p_name}»...")

            # 4. Принудительно заставляем Qt отрисовать всё мгновенно (0 мс задержки)
            QApplication.processEvents()

            # 5. Запускаем процедуру переключения через таймер
            QTimer.singleShot(40, lambda: self._execute_hot_switch(old_id, profile_id))
            return

        # Обычный запуск одиночного подключения (когда ни один VPN не был активен)
        # 1. Мгновенно переводим карточку в состояние подключения (0 мс)
        if profile_id in self.cards:
            self.cards[profile_id].update_state(
                VPNState.CONNECTING,
                custom_status="⏳ Подключение...",
                custom_btn="Подключение..."
            )

        # 2. Мгновенно переводим нижнюю статусную панель и трей
        p_name = profile.get("name", "VPN")
        self.status_pill.setText("● Подключение...")
        self.status_pill.setStyleSheet(
            "background-color: #451a03; color: #fbbf24; border: 1px solid #d97706; "
            "border-radius: 12px; padding: 4px 14px; font-weight: 800; font-size: 11px;"
        )
        self.lbl_active_proto.setText(f"Возведение плотины «{p_name}»...")
        self._update_tray_state(VPNState.CONNECTING, p_name)

        # 3. Принудительно заставляем Qt отрисовать всё мгновенно (0 мс)
        QApplication.processEvents()

        # 4. Запускаем процедуру инициализации туннеля через микро-таймер,
        # чтобы UI гарантированно перерисовался до любых системных вызовов
        QTimer.singleShot(40, lambda: self._start_profile_tunnel(profile_id))

    def _execute_hot_switch(self, old_id: str, new_id: str):
        # 1. Синхронно и чисто останавливаем старый туннель
        self._on_disconnect_profile(old_id, wait=True)
        if old_id in self.cards:
            self.cards[old_id].update_state(VPNState.DISCONNECTED)
        self.active_profile_id = None
        QApplication.processEvents()

        # 2. Гарантированно глушим любые активные демоны перед стартом
        if self.amnezia_launcher.is_running():
            self.amnezia_launcher.stop_connection(wait=True)
        if self.openconnect_launcher.is_running():
            self.openconnect_launcher.stop_connection(wait=True)

        # 3. Стартуем новый профиль
        self._start_profile_tunnel(new_id)

    def _start_profile_tunnel(self, profile_id: str):
        profile = settings.get_profile(profile_id)
        if not profile:
            return

        self.active_profile_id = profile_id
        proto = profile.get("proto", "amnezia")

        if profile_id in self.cards:
            self.cards[profile_id].update_state(VPNState.CONNECTING)

        if proto == "amnezia":
            content = profile.get("config_content", "").strip()
            cfg_path = profile.get("config_path", "").strip()
            iface = profile.get("interface", "").strip() or "awg0"
            obf = profile.get("obfuscation", {})

            # Если нет сохраненного текста конфигурации и нет исходного файла
            if not content and (not cfg_path or not os.path.isfile(cfg_path)):
                QMessageBox.warning(
                    self,
                    "Конфигурация не найдена",
                    f"Для подключения «{profile.get('name', 'AmneziaWG')}» не задана конфигурация.\n\n"
                    "Пожалуйста, откройте «⚙ Настройки» подключения и укажите .conf файл или вставьте параметры."
                )
                if profile_id in self.cards:
                    self.cards[profile_id].update_state(VPNState.ERROR)
                self.active_profile_id = None
                return

            ok = self.amnezia_launcher.start_connection(
                config_content=content,
                config_path=cfg_path,
                obfuscation_overrides=obf,
                interface_name=iface
            )
            if not ok:
                if profile_id in self.cards:
                    self.cards[profile_id].update_state(VPNState.ERROR)
                self.active_profile_id = None
        else:
            server = profile.get("server", "")
            port = int(profile.get("port", 443))
            cam = profile.get("camouflage", "")
            user = profile.get("username", "")
            pwd = profile.get("password", "")

            # Если пароль отсутствует в профиле, проверяем глобальный кэш
            if not pwd:
                pwd = settings.get_password("openconnect_password")

            # Если пароль всё ещё не задан, запрашиваем через модальное окно
            if not pwd:
                prompt = PasswordPromptDialog(
                    profile_name=profile.get("name", "OpenConnect"),
                    username=user or "vpn_user",
                    server=f"{server}:{port}",
                    parent=self
                )
                if prompt.exec() != QDialog.Accepted:
                    if profile_id in self.cards:
                        self.cards[profile_id].update_state(VPNState.DISCONNECTED)
                    self.active_profile_id = None
                    return

                pwd = prompt.get_password()
                if not pwd:
                    if profile_id in self.cards:
                        self.cards[profile_id].update_state(VPNState.DISCONNECTED)
                    self.active_profile_id = None
                    return

                if prompt.should_remember():
                    profile["password"] = pwd
                    profile["remember_password"] = True
                    settings.save_profile(profile)
                    settings.set_password(pwd, "openconnect_password")

            self.openconnect_launcher.start_connection(
                server=server,
                port=port,
                protocol=profile.get("protocol", "anyconnect"),
                camouflage_secret=cam,
                username=user,
                password=pwd,
                allow_insecure_cert=False
            )

    def _on_disconnect_profile(self, profile_id: str, wait: bool = False):
        profile = settings.get_profile(profile_id)
        if not profile:
            return

        p_name = profile.get("name", "VPN")

        if profile_id in self.cards:
            if wait:
                self.cards[profile_id].update_state(VPNState.DISCONNECTED)
            else:
                self.cards[profile_id].update_state(
                    VPNState.DISCONNECTING,
                    custom_status="⏳ Отключение...",
                    custom_btn="Отключение..."
                )

        if not wait:
            self.status_pill.setText("● Отключение...")
            self.status_pill.setStyleSheet(
                "background-color: #451a03; color: #fbbf24; border: 1px solid #d97706; "
                "border-radius: 12px; padding: 4px 14px; font-weight: 800; font-size: 11px;"
            )
            self.lbl_active_proto.setText(f"Разбор плотины «{p_name}»...")
            self._update_tray_state(VPNState.DISCONNECTING, p_name)
            QApplication.processEvents()

        proto = profile.get("proto", "amnezia")
        launcher = self.amnezia_launcher if proto == "amnezia" else self.openconnect_launcher

        if wait:
            launcher.stop_connection(wait=True)
        else:
            QTimer.singleShot(40, lambda: launcher.stop_connection(wait=False))

    def _wire_signals(self):
        # AmneziaWG сигналы
        self.amnezia_launcher.state_changed.connect(lambda s: self._on_state_change("AmneziaWG", s))
        self.amnezia_launcher.log_received.connect(self.log_viewer.append_log)
        self.amnezia_launcher.error_occurred.connect(self._on_error)

        # OpenConnect сигналы
        self.openconnect_launcher.state_changed.connect(lambda s: self._on_state_change("OpenConnect", s))
        self.openconnect_launcher.log_received.connect(self.log_viewer.append_log)
        self.openconnect_launcher.error_occurred.connect(self._on_error)

    def _on_state_change(self, vpn_name: str, state_value: str):
        state = VPNState(state_value)

        active_prof = settings.get_profile(self.active_profile_id) if self.active_profile_id else None
        active_proto = active_prof.get("proto", "amnezia") if active_prof else None
        active_launcher_name = "AmneziaWG" if active_proto == "amnezia" else ("OpenConnect" if active_proto == "openconnect" else None)
        is_current_launcher = (self.active_profile_id is not None) and (vpn_name == active_launcher_name)

        # Обработка событий от предыдущего/фонового демона, завершающего работу
        if not is_current_launcher:
            if state == VPNState.DISCONNECTED:
                for pid, card in self.cards.items():
                    prof = settings.get_profile(pid)
                    if prof:
                        p_proto = prof.get("proto", "amnezia")
                        p_launcher = "AmneziaWG" if p_proto == "amnezia" else "OpenConnect"
                        if p_launcher == vpn_name and card.state in (VPNState.DISCONNECTING, VPNState.CONNECTING):
                            card.update_state(VPNState.DISCONNECTED)
            return

        self._update_status_pill_style(state_value)
        self._update_tray_state(state, vpn_name)

        if self.active_profile_id and self.active_profile_id in self.cards:
            self.cards[self.active_profile_id].update_state(state)

        if state == VPNState.CONNECTED:
            p = settings.get_profile(self.active_profile_id)
            p_name = p.get("name", vpn_name) if p else vpn_name
            self.lbl_active_proto.setText(f"Активно: {p_name} ({vpn_name})")
            self._connected_start_time = time.time()
            self.timer.start()

        elif state == VPNState.DISCONNECTED:
            self.lbl_active_proto.setText("Речной трафик идёт открыто")
            self.timer.stop()
            self.lbl_timer.setText("00:00:00")
            if self.active_profile_id and self.active_profile_id in self.cards:
                self.cards[self.active_profile_id].update_state(VPNState.DISCONNECTED)
            self.active_profile_id = None

        elif state == VPNState.ERROR:
            self.timer.stop()
            if self.active_profile_id and self.active_profile_id in self.cards:
                self.cards[self.active_profile_id].update_state(VPNState.ERROR)

    def _update_status_pill_style(self, state: str):
        if state == VPNState.CONNECTED.value:
            text = "● Плотина стабильна"
            bg, fg, border = "rgba(16, 185, 129, 0.15)", "#34d399", "rgba(16, 185, 129, 0.40)"
        elif state == VPNState.CONNECTING.value:
            text = "● Возведение плотины..."
            bg, fg, border = "rgba(217, 119, 6, 0.15)", "#fbbf24", "rgba(217, 119, 6, 0.40)"
        elif state == VPNState.ERROR.value:
            text = "● Протечка в плотине!"
            bg, fg, border = "rgba(239, 68, 68, 0.15)", "#f87171", "rgba(239, 68, 68, 0.40)"
        else:
            text = "○ Плотина не построена"
            bg, fg, border = "rgba(255, 255, 255, 0.04)", "#64748b", "rgba(255, 255, 255, 0.08)"

        self.status_pill.setText(text)
        self.status_pill.setStyleSheet(
            f"background-color: {bg}; color: {fg}; border: 1px solid {border}; "
            f"border-radius: 12px; padding: 4px 14px; font-weight: 800; font-size: 11px;"
        )

    def _update_timer_label(self):
        if self._connected_start_time > 0:
            elapsed = int(time.time() - self._connected_start_time)
            hrs = elapsed // 3600
            mins = (elapsed % 3600) // 60
            secs = elapsed % 60
            self.lbl_timer.setText(f"{hrs:02d}:{mins:02d}:{secs:02d}")

    def _on_error(self, message: str):
        self.log_viewer.append_log(f"ВНИМАНИЕ: {message}", "error")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        settings.set("window_width", self.width())
        settings.set("window_height", self.height())

    def closeEvent(self, event):
        # 1. Если вызвано принудительное завершение через меню трея
        if getattr(self, "_force_quitting", False):
            self._clean_shutdown(wait=True)
            if hasattr(self, "tray_icon"):
                self.tray_icon.hide()
            event.accept()
            return

        is_vpn_active = self.amnezia_launcher.is_running() or self.openconnect_launcher.is_running()
        if is_vpn_active:
            # 2. Если VPN активен — сворачиваем в трей по крестику
            event.ignore()
            self.hide()
            if hasattr(self, "tray_icon") and not getattr(self, "_tray_minimized_hint_shown", False):
                self.tray_icon.showMessage(
                    "БобрДобр свёрнут в трей",
                    "VPN-соединение остаётся активным в фоне. Кликните по бобру в трее для открытия окна.",
                    QSystemTrayIcon.Information,
                    3000
                )
                self._tray_minimized_hint_shown = True
        else:
            # 3. Если VPN не активен — обычное закрытие программы
            self._clean_shutdown(wait=True)
            if hasattr(self, "tray_icon"):
                self.tray_icon.hide()
            event.accept()
            QApplication.instance().quit()

    # ==========================================
    # GitHub Updates
    # ==========================================
    def _start_silent_update_check(self):
        """Starts background silent check for updates on GitHub."""
        if self._update_checker_thread and self._update_checker_thread.isRunning():
            return
        self._update_checker_thread = GitHubUpdateCheckerThread(
            repo=GITHUB_REPO, current_version=APP_VERSION, timeout=6, parent=self
        )
        self._update_checker_thread.result_ready.connect(self._on_silent_update_result)
        self._update_checker_thread.start()

    def _on_silent_update_result(self, res: dict):
        """Handles background silent update check result."""
        if res.get("update_available"):
            self._latest_update_info = res
            new_ver = res.get("latest_version", "")
            self.btn_update_available.setText(f"🚀 Доступно v{new_ver}")
            self.btn_update_available.setVisible(True)
            if hasattr(self, "action_tray_update"):
                self.action_tray_update.setText(f"🚀  Доступна новая версия v{new_ver}!")
                self.action_tray_update.setVisible(True)

    def _on_update_available_clicked(self):
        """Opens GitHubUpdateDialog when user clicks the update banner or tray action."""
        if self._latest_update_info and self._latest_update_info.get("update_available"):
            dlg = GitHubUpdateDialog(self, self._latest_update_info, self.app_icon)
            dlg.exec()
        else:
            self._check_updates_interactive()

    def _check_updates_interactive(self):
        """User-triggered interactive check for updates."""
        if self._update_checker_thread and self._update_checker_thread.isRunning():
            return

        if hasattr(self, "ver_badge"):
            self.ver_badge.setText("⏳ Проверка...")

        self._update_checker_thread = GitHubUpdateCheckerThread(
            repo=GITHUB_REPO, current_version=APP_VERSION, timeout=8, parent=self
        )
        self._update_checker_thread.result_ready.connect(self._on_interactive_update_result)
        self._update_checker_thread.start()

    def _on_interactive_update_result(self, res: dict):
        """Handles result of user-initiated update check."""
        if hasattr(self, "ver_badge"):
            self.ver_badge.setText(f"v{APP_VERSION}")

        if res.get("update_available"):
            self._latest_update_info = res
            new_ver = res.get("latest_version", "")
            self.btn_update_available.setText(f"🚀 Доступно v{new_ver}")
            self.btn_update_available.setVisible(True)
            if hasattr(self, "action_tray_update"):
                self.action_tray_update.setText(f"🚀  Доступна новая версия v{new_ver}!")
                self.action_tray_update.setVisible(True)

            dlg = GitHubUpdateDialog(self, res, self.app_icon)
            dlg.exec()
        elif res.get("error"):
            QMessageBox.warning(
                self,
                "Проверка обновлений",
                f"Не удалось связаться с сервером GitHub для проверки обновлений:\n\n{res['error']}\n\n"
                "Пожалуйста, проверьте подключение к интернету."
            )
        else:
            QMessageBox.information(
                self,
                "Обновлений не требуется",
                f"У вас установлена самая актуальная версия БобрДобр (v{APP_VERSION}).\n\n"
                "Сетевые плотины в полной безопасности!"
            )


class GlobalButtonHoverFilter(QObject):
    """Ensures every clickable button, checkbox, and radio button in the app displays PointingHandCursor on hover."""
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Enter:
            if isinstance(obj, (QAbstractButton, QPushButton, QRadioButton, QCheckBox)):
                obj.setCursor(Qt.PointingHandCursor)
        return super().eventFilter(obj, event)


_SINGLE_INSTANCE_MUTEX = None


def check_single_instance() -> bool:
    """Returns True if this is the only running instance.
    If another instance is already running on Windows, restores its window and returns False."""
    global _SINGLE_INSTANCE_MUTEX
    if not is_windows():
        return True
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        mode_str = "Installed" if is_installed_mode() else "Portable"
        mutex_name = f"Global\\BobrDobr_VPN_SingleInstance_{mode_str}_v1"
        _SINGLE_INSTANCE_MUTEX = kernel32.CreateMutexW(None, False, mutex_name)
        if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            def enum_cb(h, _):
                length = user32.GetWindowTextLengthW(h)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(h, buff, length + 1)
                    title = buff.value
                    if "БобрДобр" in title and "Visual Studio" not in title:
                        user32.ShowWindow(h, 9)  # SW_RESTORE
                        user32.SetForegroundWindow(h)
                        return False
                return True
            WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
            return False
        return True
    except Exception:
        return True


def main():
    if is_windows():
        if not check_single_instance():
            sys.exit(0)
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("BobrDobr.VPN.Client.1")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("BobrDobrVPN")
    app.setOrganizationName("BobrDobr")
    app.setQuitOnLastWindowClosed(False)

    # Устанавливаем глобальную иконку приложения для всех окон и диалогов
    ico_candidates = [
        os.path.join(get_base_dir(), "assets", "beaver.ico"),
        os.path.join(get_base_dir(), "src", "assets", "beaver.ico"),
        os.path.join(os.path.dirname(__file__), "assets", "beaver.ico"),
        os.path.join(os.getcwd(), "assets", "beaver.ico"),
        os.path.join(os.getcwd(), "src", "assets", "beaver.ico"),
    ]
    for p in ico_candidates:
        if os.path.isfile(p):
            app_icon = QIcon(p)
            if not app_icon.isNull():
                app.setWindowIcon(app_icon)
                break

    # Включаем стиль Fusion и тёмную палитру для устранения белых системных фонов в Windows
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#0f1416"))
    palette.setColor(QPalette.WindowText, QColor("#e2e8f0"))
    palette.setColor(QPalette.Base, QColor("#121a1d"))
    palette.setColor(QPalette.AlternateBase, QColor("#182226"))
    palette.setColor(QPalette.ToolTipBase, QColor("#182226"))
    palette.setColor(QPalette.ToolTipText, QColor("#e2e8f0"))
    palette.setColor(QPalette.Text, QColor("#f8fafc"))
    palette.setColor(QPalette.Button, QColor("#1a252a"))
    palette.setColor(QPalette.ButtonText, QColor("#e2e8f0"))
    palette.setColor(QPalette.BrightText, QColor("#f87171"))
    palette.setColor(QPalette.Link, QColor("#38bdf8"))
    palette.setColor(QPalette.Highlight, QColor("#d97706"))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor("#64748b"))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#64748b"))
    app.setPalette(palette)

    app.setStyleSheet(get_stylesheet())

    # Глобальный фильтр для курсора руки на всех кнопках интерфейса
    hover_filter = GlobalButtonHoverFilter(app)
    app.installEventFilter(hover_filter)

    window = MainWindow()
    app.aboutToQuit.connect(lambda: window._clean_shutdown(wait=True))
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
