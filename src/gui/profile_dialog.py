import os
from datetime import datetime
from typing import Dict, Any, Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QSpinBox, QCheckBox,
    QFileDialog, QGroupBox, QStackedWidget, QWidget, QMessageBox,
    QPlainTextEdit, QSizePolicy, QListView, QFrame, QApplication, QScrollArea
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer
from core.amnezia import AmneziaWGLauncher
from utils.config_store import settings
from utils.platform_helper import get_base_dir
from gui.styles import (
    get_amnezia_icon, get_openconnect_icon, get_subscription_icon,
    get_amnezia_pixmap, get_openconnect_pixmap, get_subscription_pixmap
)
from utils.subscription_manager import (
    SubscriptionManager, SubscriptionError, format_subscription_profile_name
)


class PasswordPromptDialog(QDialog):
    """
    Быстрый диалог авторизации OpenConnect, если пароль не сохранён заранее.
    """
    def __init__(self, profile_name: str, username: str, server: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Авторизация плотины | OpenConnect")
        self.resize(500, 260)
        self.setMinimumSize(460, 240)
        self.setStyleSheet("""
            QDialog {
                background-color: #0c1316;
                color: #e2e8f0;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(16)

        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)
        title_lbl = QLabel(f"🔒 Подключение к плотине: {profile_name}")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: 800; color: #34d399;")
        header_layout.addWidget(title_lbl)

        info_lbl = QLabel(
            f"Шлюз: <span style='color: #e2e8f0; font-weight: 600;'>{server}</span>  •  "
            f"Позывной: <span style='color: #38bdf8; font-weight: 600;'>{username}</span>"
        )
        info_lbl.setTextFormat(Qt.RichText)
        info_lbl.setStyleSheet("font-size: 12px; color: #94a3b8;")
        header_layout.addWidget(info_lbl)
        layout.addLayout(header_layout)

        # Поле пароля
        pwd_group = QGroupBox("Стук хвостом (Пароль авторизации)")
        pwd_layout = QVBoxLayout(pwd_group)
        pwd_layout.setSpacing(10)

        pwd_row = QHBoxLayout()
        pwd_row.setSpacing(8)
        self.input_pwd = QLineEdit()
        self.input_pwd.setFixedHeight(38)
        self.input_pwd.setEchoMode(QLineEdit.Password)
        self.input_pwd.setPlaceholderText("Введите пароль доступа...")
        pwd_row.addWidget(self.input_pwd, 1)

        self.btn_toggle_pwd = QPushButton("Показать")
        self.btn_toggle_pwd.setObjectName("btn_secondary")
        self.btn_toggle_pwd.setCursor(Qt.PointingHandCursor)
        self.btn_toggle_pwd.setFixedHeight(38)
        self.btn_toggle_pwd.setFixedWidth(92)
        self.btn_toggle_pwd.clicked.connect(self._toggle_pwd_visibility)
        pwd_row.addWidget(self.btn_toggle_pwd, 0)
        pwd_layout.addLayout(pwd_row)

        self.cb_remember = QCheckBox("Запомнить пароль в этом профиле")
        self.cb_remember.setChecked(True)
        self.cb_remember.setCursor(Qt.PointingHandCursor)
        pwd_layout.addWidget(self.cb_remember)

        layout.addWidget(pwd_group)

        # Кнопки действия
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("Отмена")
        btn_cancel.setObjectName("btn_secondary")
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.setFixedHeight(38)
        btn_cancel.setFixedWidth(110)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_connect = QPushButton("Сплавить лес")
        btn_connect.setObjectName("btn_primary")
        btn_connect.setCursor(Qt.PointingHandCursor)
        btn_connect.setFixedHeight(38)
        btn_connect.setFixedWidth(150)
        btn_connect.clicked.connect(self._on_submit)
        btn_layout.addWidget(btn_connect)

        layout.addLayout(btn_layout)
        self.input_pwd.setFocus()

    def _toggle_pwd_visibility(self):
        if self.input_pwd.echoMode() == QLineEdit.Password:
            self.input_pwd.setEchoMode(QLineEdit.Normal)
            self.btn_toggle_pwd.setText("Скрыть")
        else:
            self.input_pwd.setEchoMode(QLineEdit.Password)
            self.btn_toggle_pwd.setText("Показать")

    def _on_submit(self):
        pwd = self.input_pwd.text().strip()
        if not pwd:
            QMessageBox.warning(self, "Внимание", "Пожалуйста, введите пароль для входа в гидроузел.")
            self.input_pwd.setFocus()
            return
        self.accept()

    def get_password(self) -> str:
        return self.input_pwd.text()

    def should_remember(self) -> bool:
        return self.cb_remember.isChecked()


class ProfileDialog(QDialog):
    """
    Диалоговое окно создания и редактирования профилей VPN (AmneziaWG и OpenConnect)
    с автономным сохранением всех параметров конфигурации в settings.json.
    """

    def __init__(self, profile: Optional[Dict[str, Any]] = None, parent=None):
        super().__init__(parent)
        self.profile = dict(profile) if profile else {}
        self.is_edit = bool(self.profile and self.profile.get("id"))
        self.is_subscription_synced = False
        self.synced_profiles_count = 0

        title = "Настройка подключения" if self.is_edit else "Создать новое подключение"
        self.setWindowTitle(title)
        self.resize(640, 720)
        self.setMinimumSize(600, 660)
        self._name_user_customized = self.is_edit and bool(self.profile.get("name"))
        self.setStyleSheet("""
            QDialog {
                background-color: #0c1316;
                color: #e2e8f0;
            }
        """)

        if parent and hasattr(parent, "app_icon") and not parent.app_icon.isNull():
            self.setWindowIcon(parent.app_icon)

        self._init_ui()
        if self.is_edit:
            self._load_existing_data()
        else:
            self._update_awg_preview()

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(24, 20, 24, 20)
        root_layout.setSpacing(14)

        # 0. Верхняя брендовая панель заголовка диалога
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        icon_lbl = QLabel()
        candidates = [
            os.path.join(get_base_dir(), "assets", "beaver.svg"),
            os.path.join(get_base_dir(), "src", "assets", "beaver.svg"),
            os.path.join(os.path.dirname(__file__), "..", "assets", "beaver.svg"),
            os.path.join(os.path.dirname(__file__), "assets", "beaver.svg"),
            os.path.join(os.getcwd(), "assets", "beaver.svg"),
            os.path.join(os.getcwd(), "src", "assets", "beaver.svg"),
        ]
        if self.parent() and hasattr(self.parent(), "beaver_icon_path") and self.parent().beaver_icon_path:
            candidates.insert(0, self.parent().beaver_icon_path)

        icon_path = ""
        for c in candidates:
            if c and os.path.isfile(c):
                icon_path = os.path.abspath(c)
                break

        if icon_path:
            renderer = QSvgRenderer(icon_path)
            pixmap = QPixmap(36, 36)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            icon_lbl.setPixmap(pixmap)
        header_layout.addWidget(icon_lbl)

        header_text_layout = QVBoxLayout()
        header_text_layout.setSpacing(2)

        dlg_title = QLabel("Настройка подключения" if self.is_edit else "Создать новое подключение")
        dlg_title.setStyleSheet("font-size: 18px; font-weight: 800; color: #f8fafc;")
        header_text_layout.addWidget(dlg_title)

        dlg_subtitle = QLabel("Конфигурация параметров защищённого гидроузла BobrDobr VPN")
        dlg_subtitle.setStyleSheet("font-size: 11px; color: #94a3b8; font-weight: 500;")
        header_text_layout.addWidget(dlg_subtitle)

        header_layout.addLayout(header_text_layout)
        header_layout.addStretch()
        root_layout.addLayout(header_layout)

        # 1. Основные параметры (Тип и Название)
        base_group = QGroupBox("Параметры профиля")
        base_form = QFormLayout(base_group)
        self.base_form = base_form
        base_form.setSpacing(14)
        base_form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        base_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.combo_proto = QComboBox()
        self.combo_proto.setFixedHeight(38)
        self.combo_proto.setView(QListView())
        self.combo_proto.setSizeAdjustPolicy(QComboBox.AdjustToContentsOnFirstShow)
        self.combo_proto.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        amz_icon = get_amnezia_icon()
        oc_icon = get_openconnect_icon()
        sub_icon = get_subscription_icon()

        if not amz_icon.isNull():
            self.combo_proto.addItem(amz_icon, "  AmneziaWG", "amnezia")
        else:
            self.combo_proto.addItem("⚡  AmneziaWG", "amnezia")
        if not oc_icon.isNull():
            self.combo_proto.addItem(oc_icon, "  OpenConnect", "openconnect")
        else:
            self.combo_proto.addItem("🔒  OpenConnect", "openconnect")

        if not self.is_edit:
            if not sub_icon.isNull():
                self.combo_proto.addItem(sub_icon, "  Подписка (BobrDobr VPN)", "subscription")
            else:
                self.combo_proto.addItem("🔑  Подписка (BobrDobr VPN)", "subscription")

        self.combo_proto.currentIndexChanged.connect(self._on_proto_changed)
        base_form.addRow("Протокол:", self.combo_proto)

        self.input_name = QLineEdit()
        self.input_name.setFixedHeight(38)
        self.input_name.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.input_name.setPlaceholderText("Например: Основной Шлюз или Рабочий VPN")
        self.input_name.textEdited.connect(self._on_name_text_edited)
        base_form.addRow("Название подключения:", self.input_name)

        root_layout.addWidget(base_group)

        # 2. Динамический стек для страниц протоколов
        self.stack = QStackedWidget()

        # Страница AmneziaWG
        self.page_amnezia = self._create_amnezia_page()
        self.stack.addWidget(self.page_amnezia)

        # Страница OpenConnect
        self.page_openconnect = self._create_openconnect_page()
        self.stack.addWidget(self.page_openconnect)

        # Страница Подписки (BobrDobr VPN)
        if not self.is_edit:
            self.page_subscription = self._create_subscription_page()
            self.stack.addWidget(self.page_subscription)

        root_layout.addWidget(self.stack, 1)

        # 3. Кнопки сохранения и отмены
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 10, 0, 0)
        btn_layout.setSpacing(12)
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Отмена")
        self.btn_cancel.setObjectName("btn_secondary")
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.setFixedHeight(38)
        self.btn_cancel.setMinimumWidth(110)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("💾  Сохранить подключение" if self.is_edit else "+  Сохранить подключение")
        self.btn_save.setObjectName("btn_primary")
        self.btn_save.setCursor(Qt.PointingHandCursor)
        self.btn_save.setFixedHeight(38)
        self.btn_save.setMinimumWidth(220)
        self.btn_save.clicked.connect(self._on_save_clicked)
        btn_layout.addWidget(self.btn_save)

        root_layout.addLayout(btn_layout)

    def _create_amnezia_page(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        group = QGroupBox("Параметры туннеля AmneziaWG (.conf)")
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(16, 22, 16, 16)
        group_layout.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        # Ряд импорта файла .conf
        file_row = QHBoxLayout()
        file_row.setSpacing(8)
        self.input_awg_path = QLineEdit()
        self.input_awg_path.setFixedHeight(38)
        self.input_awg_path.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.input_awg_path.setPlaceholderText("Импортировать .conf файл конфигурации...")
        file_row.addWidget(self.input_awg_path, 1)

        btn_browse = QPushButton("Обзор...")
        btn_browse.setObjectName("btn_secondary")
        btn_browse.setCursor(Qt.PointingHandCursor)
        btn_browse.setFixedHeight(38)
        btn_browse.setFixedWidth(92)
        btn_browse.clicked.connect(self._browse_conf_file)
        file_row.addWidget(btn_browse, 0)
        form.addRow("Импорт из файла:", file_row)

        self.input_awg_iface = QLineEdit("bobr0")
        self.input_awg_iface.setFixedHeight(38)
        self.input_awg_iface.setPlaceholderText("bobr0")
        self.input_awg_iface.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        form.addRow("Имя интерфейса:", self.input_awg_iface)
        group_layout.addLayout(form)

        # Заголовок поля конфигурации
        lbl_conf_title = QLabel("Конфигурация туннеля (.conf):")
        lbl_conf_title.setStyleSheet("color: #cbd5e1; font-weight: 600; font-size: 13px; margin-top: 2px;")
        group_layout.addWidget(lbl_conf_title)

        # Единый блок редактора со встроенной в его низ плашкой статуса
        editor_container = QFrame()
        editor_container.setObjectName("awg_editor_container")
        editor_layout = QVBoxLayout(editor_container)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)

        # Редактор конфигурации .conf
        self.text_awg_config = QPlainTextEdit()
        self.text_awg_config.setMinimumHeight(120)
        self.text_awg_config.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.text_awg_config.setPlaceholderText(
            "# Вставьте или отредактируйте параметры AmneziaWG (.conf):\n"
            "[Interface]\n"
            "Address = 10.8.0.2/32\n"
            "PrivateKey = ...\n"
            "DNS = 1.1.1.1\n"
            "Jc = 4\n"
            "Jmin = 40\n"
            "Jmax = 70\n"
            "S1 = 15\n"
            "S2 = 30\n"
            "H1 = 1\n"
            "H2 = 2\n"
            "H3 = 3\n"
            "H4 = 4\n\n"
            "[Peer]\n"
            "PublicKey = ...\n"
            "Endpoint = vpn.example.com:51820\n"
            "AllowedIPs = 0.0.0.0/0\n"
        )
        self.text_awg_config.textChanged.connect(self._on_awg_text_changed)
        editor_layout.addWidget(self.text_awg_config, 1)

        # Нижняя плашка статуса, вписанная строго в нижнюю кромку блока редактора
        status_footer = QFrame()
        status_footer.setObjectName("awg_status_footer")
        status_footer_layout = QHBoxLayout(status_footer)
        status_footer_layout.setContentsMargins(12, 6, 12, 6)
        status_footer_layout.setSpacing(8)

        lbl_status_prefix = QLabel("Статус:")
        lbl_status_prefix.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 700; text-transform: uppercase;")
        status_footer_layout.addWidget(lbl_status_prefix)

        self.lbl_awg_status = QLabel("○ Конфигурация не загружена")
        self.lbl_awg_status.setStyleSheet("font-size: 11px; color: #94a3b8; font-weight: 600;")
        status_footer_layout.addWidget(self.lbl_awg_status, 1)

        editor_layout.addWidget(status_footer, 0)
        group_layout.addWidget(editor_container, 1)

        layout.addWidget(group, 1)
        return widget

    def _create_openconnect_page(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        group = QGroupBox("Шлюз и авторизация OpenConnect")
        form = QFormLayout(group)
        form.setSpacing(14)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.input_oc_server = QLineEdit()
        self.input_oc_server.setFixedHeight(38)
        self.input_oc_server.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.input_oc_server.setPlaceholderText("vpn.example.com")
        form.addRow("Адрес сервера:", self.input_oc_server)

        self.spin_oc_port = QSpinBox()
        self.spin_oc_port.setFixedHeight(38)
        self.spin_oc_port.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.spin_oc_port.setRange(1, 65535)
        self.spin_oc_port.setValue(443)
        form.addRow("Порт шлюза:", self.spin_oc_port)

        self.input_oc_cam = QLineEdit()
        self.input_oc_cam.setFixedHeight(38)
        self.input_oc_cam.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.input_oc_cam.setPlaceholderText("Секретный ключ (например secret_token)")
        form.addRow("Маскировка (Camouflage):", self.input_oc_cam)

        self.input_oc_user = QLineEdit()
        self.input_oc_user.setFixedHeight(38)
        self.input_oc_user.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.input_oc_user.setPlaceholderText("vpn_user")
        self.input_oc_user.textChanged.connect(self._on_oc_user_text_changed)
        form.addRow("Позывной (Логин):", self.input_oc_user)

        # Ряд пароля
        pwd_row = QHBoxLayout()
        pwd_row.setSpacing(8)
        self.input_oc_pwd = QLineEdit()
        self.input_oc_pwd.setFixedHeight(38)
        self.input_oc_pwd.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.input_oc_pwd.setEchoMode(QLineEdit.Password)
        self.input_oc_pwd.setPlaceholderText("Пароль доступа")
        pwd_row.addWidget(self.input_oc_pwd, 1)

        self.btn_toggle_pwd = QPushButton("Показать")
        self.btn_toggle_pwd.setObjectName("btn_secondary")
        self.btn_toggle_pwd.setCursor(Qt.PointingHandCursor)
        self.btn_toggle_pwd.setFixedHeight(38)
        self.btn_toggle_pwd.setFixedWidth(92)
        self.btn_toggle_pwd.clicked.connect(self._toggle_pwd_visibility)
        pwd_row.addWidget(self.btn_toggle_pwd, 0)
        form.addRow("Стук хвостом (Пароль):", pwd_row)

        self.cb_remember_pwd = QCheckBox("Запомнить пароль в профиле")
        self.cb_remember_pwd.setChecked(True)
        self.cb_remember_pwd.setCursor(Qt.PointingHandCursor)
        form.addRow("", self.cb_remember_pwd)

        layout.addWidget(group)
        layout.addStretch()
        return widget

    def _create_subscription_page(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # 1. Группа ввода ссылки подписки
        group = QGroupBox("Параметры подписки (BobrDobr VPN)")
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(16, 18, 16, 16)
        group_layout.setSpacing(12)

        lbl_desc = QLabel(
            "Вставьте персональную ссылку подписки из личного кабинета BobrDobr VPN. "
            "Все доступные протоколы (AmneziaWG и OpenConnect) будут импортированы и обновлены автоматически."
        )
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet("color: #94a3b8; font-size: 12px; line-height: 1.4;")
        group_layout.addWidget(lbl_desc)

        # Ряд ввода ссылки подписки
        url_row = QHBoxLayout()
        url_row.setSpacing(8)

        self.input_sub_url = QLineEdit()
        self.input_sub_url.setFixedHeight(38)
        self.input_sub_url.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.input_sub_url.setPlaceholderText("https://bobr.netphoenix.ru/api/v1/sub/...")
        saved_sub_url = (settings.get("subscription_url") or "").strip()
        if saved_sub_url:
            self.input_sub_url.setText(saved_sub_url)
        url_row.addWidget(self.input_sub_url, 1)

        self.btn_sub_paste = QPushButton("📋 Вставить")
        self.btn_sub_paste.setObjectName("btn_secondary")
        self.btn_sub_paste.setCursor(Qt.PointingHandCursor)
        self.btn_sub_paste.setFixedHeight(38)
        self.btn_sub_paste.setFixedWidth(100)
        self.btn_sub_paste.clicked.connect(self._on_sub_paste_clicked)
        url_row.addWidget(self.btn_sub_paste, 0)

        group_layout.addLayout(url_row)

        # Ряд кнопки проверки
        action_row = QHBoxLayout()
        action_row.setSpacing(8)

        self.btn_sub_fetch = QPushButton("🔍 Проверить и загрузить")
        self.btn_sub_fetch.setObjectName("btn_secondary")
        self.btn_sub_fetch.setCursor(Qt.PointingHandCursor)
        self.btn_sub_fetch.setFixedHeight(38)
        self.btn_sub_fetch.setMinimumWidth(190)
        self.btn_sub_fetch.clicked.connect(self._on_sub_fetch_clicked)
        action_row.addWidget(self.btn_sub_fetch)
        action_row.addStretch()

        group_layout.addLayout(action_row)
        layout.addWidget(group)

        # 2. Панель статуса и предпросмотра
        self.sub_preview_frame = QFrame()
        self.sub_preview_frame.setObjectName("sub_preview_frame")
        self.sub_preview_frame.setStyleSheet("""
            QFrame#sub_preview_frame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #141c22, stop:1 #0c1215);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-top: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 10px;
            }
        """)
        preview_layout = QVBoxLayout(self.sub_preview_frame)
        preview_layout.setContentsMargins(14, 14, 14, 14)
        preview_layout.setSpacing(10)

        # Верхний ряд статуса
        status_row = QHBoxLayout()
        status_row.setSpacing(10)

        self.lbl_sub_status_badge = QLabel("○ Подписка не проверена")
        self.lbl_sub_status_badge.setStyleSheet("""
            color: #94a3b8;
            background-color: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.10);
            border-radius: 12px;
            padding: 4px 12px;
            font-weight: 700;
            font-size: 11px;
        """)
        status_row.addWidget(self.lbl_sub_status_badge)

        self.lbl_sub_user_info = QLabel("")
        self.lbl_sub_user_info.setTextFormat(Qt.RichText)
        self.lbl_sub_user_info.setWordWrap(True)
        self.lbl_sub_user_info.setStyleSheet("color: #cbd5e1; font-size: 12px; background: transparent; border: none;")
        status_row.addWidget(self.lbl_sub_user_info, 1)

        preview_layout.addLayout(status_row)

        # Метка ошибки
        self.lbl_sub_error = QLabel("")
        self.lbl_sub_error.setStyleSheet("color: #f87171; font-size: 12px; font-weight: 600; padding: 4px; background: transparent; border: none;")
        self.lbl_sub_error.setWordWrap(True)
        self.lbl_sub_error.setVisible(False)
        preview_layout.addWidget(self.lbl_sub_error)

        # Заголовок списка подключений
        self.lbl_sub_conn_title = QLabel("Доступные подключения в подписке:")
        self.lbl_sub_conn_title.setStyleSheet("color: #e2e8f0; font-size: 12px; font-weight: 700; margin-top: 4px; background: transparent; border: none;")
        self.lbl_sub_conn_title.setVisible(False)
        preview_layout.addWidget(self.lbl_sub_conn_title)

        # Скролл-контейнер для обнаруженных подключений
        self.sub_scroll = QScrollArea()
        self.sub_scroll.setWidgetResizable(True)
        self.sub_scroll.setMinimumHeight(130)
        self.sub_scroll.setMaximumHeight(220)
        self.sub_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.sub_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.sub_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.sub_conn_container = QWidget()
        self.sub_conn_container.setStyleSheet("background: transparent;")
        self.sub_conn_layout = QVBoxLayout(self.sub_conn_container)
        self.sub_conn_layout.setContentsMargins(0, 2, 0, 2)
        self.sub_conn_layout.setSpacing(6)
        self.sub_scroll.setWidget(self.sub_conn_container)
        preview_layout.addWidget(self.sub_scroll, 1)

        layout.addWidget(self.sub_preview_frame, 1)

        # Если в настройках уже есть кэш подписки, отобразим его сразу
        cached_data = settings.get("subscription_cache")
        if isinstance(cached_data, dict) and cached_data.get("connections"):
            self._render_sub_preview(cached_data)

        return widget

    def _on_sub_paste_clicked(self):
        clipboard = QApplication.clipboard()
        text = clipboard.text().strip()
        if text:
            self.input_sub_url.setText(text)
            self._on_sub_fetch_clicked()

    def _on_sub_fetch_clicked(self):
        url = self.input_sub_url.text().strip()
        if not url:
            QMessageBox.warning(self, "Внимание", "Пожалуйста, введите ссылку на подписку.")
            self.input_sub_url.setFocus()
            return

        self.btn_sub_fetch.setEnabled(False)
        self.btn_sub_fetch.setText("⏳ Загрузка...")
        self.lbl_sub_status_badge.setText("⏳ Подключение...")
        self.lbl_sub_status_badge.setStyleSheet("""
            color: #fbbf24;
            background-color: rgba(217, 119, 6, 0.12);
            border: 1px solid rgba(217, 119, 6, 0.35);
            border-radius: 12px;
            padding: 4px 12px;
            font-weight: 700;
            font-size: 11px;
        """)
        QApplication.processEvents()

        try:
            data = SubscriptionManager.fetch_subscription(url)
            self._render_sub_preview(data)
            self.btn_sub_fetch.setText("✔ Проверено")
        except SubscriptionError as se:
            self._show_sub_error(str(se))
            self.btn_sub_fetch.setText("🔍 Проверить и загрузить")
        except Exception as e:
            self._show_sub_error(f"Не удалось получить данные подписки: {e}")
            self.btn_sub_fetch.setText("🔍 Проверить и загрузить")
        finally:
            self.btn_sub_fetch.setEnabled(True)

    def _render_sub_preview(self, data: Dict[str, Any]):
        while self.sub_conn_layout.count():
            item = self.sub_conn_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        user_info = data.get("user") or {}
        server_info = data.get("server") or {}
        status = str(data.get("status", "active")).strip().lower()
        expires_at = user_info.get("expires_at", "")
        username = user_info.get("username", "Пользователь")
        server_host = server_info.get("host", "")
        connections = data.get("connections", [])

        exp_display = "Бессрочно"
        if expires_at:
            try:
                dt = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
                exp_display = dt.strftime("%d.%m.%Y")
            except Exception:
                exp_display = str(expires_at)

        if status == "active":
            self.lbl_sub_status_badge.setText(f"● Активна до {exp_display}")
            self.lbl_sub_status_badge.setStyleSheet("""
                color: #34d399;
                background-color: rgba(16, 185, 129, 0.12);
                border: 1px solid rgba(16, 185, 129, 0.35);
                border-radius: 12px;
                padding: 4px 12px;
                font-weight: 700;
                font-size: 11px;
            """)
        else:
            self.lbl_sub_status_badge.setText(f"● {status.upper()} (до {exp_display})")
            self.lbl_sub_status_badge.setStyleSheet("""
                color: #f87171;
                background-color: rgba(239, 68, 68, 0.12);
                border: 1px solid rgba(239, 68, 68, 0.35);
                border-radius: 12px;
                padding: 4px 12px;
                font-weight: 700;
                font-size: 11px;
            """)

        user_txt = f"👤 Пользователь: <span style='color: #f8fafc; font-weight: 700;'>{username}</span>"
        srv_txt = f"🌐 Сервер: <span style='color: #38bdf8; font-weight: 700;'>{server_host}</span>" if server_host else ""
        self.lbl_sub_user_info.setText(f"{user_txt}   {srv_txt}")
        self.lbl_sub_user_info.setVisible(True)

        self.lbl_sub_error.setVisible(False)
        self.lbl_sub_conn_title.setText(f"Доступные подключения в подписке ({len(connections)}):")
        self.lbl_sub_conn_title.setVisible(True)

        if not connections:
            lbl_none = QLabel("Нет доступных подключений в данной подписке.")
            lbl_none.setStyleSheet("color: #94a3b8; font-size: 12px; font-style: italic;")
            self.sub_conn_layout.addWidget(lbl_none)
        else:
            for conn in connections:
                row_frame = QFrame()
                row_frame.setObjectName("sub_conn_preview_card")
                row_frame.setStyleSheet("""
                    QFrame#sub_conn_preview_card {
                        background-color: rgba(255, 255, 255, 0.03);
                        border: 1px solid rgba(255, 255, 255, 0.07);
                        border-radius: 8px;
                    }
                    QFrame#sub_conn_preview_card:hover {
                        background-color: rgba(255, 255, 255, 0.06);
                        border-color: rgba(255, 255, 255, 0.16);
                    }
                """)
                r_layout = QHBoxLayout(row_frame)
                r_layout.setContentsMargins(10, 8, 10, 8)
                r_layout.setSpacing(10)

                c_proto = str(conn.get("proto", "")).strip().lower()
                c_name = format_subscription_profile_name(conn.get("name", "VPN"))

                lbl_icon = QLabel()
                lbl_icon.setFixedSize(16, 16)
                lbl_icon.setScaledContents(True)

                if c_proto in ("awg", "amnezia"):
                    pix = get_amnezia_pixmap(16, 16)
                    if not pix.isNull():
                        lbl_icon.setPixmap(pix)
                    else:
                        lbl_icon.setText("⚡")
                    proto_label = "<span style='color: #fbbf24; font-weight: 700;'>AmneziaWG</span>"
                    desc = conn.get("endpoint") or conn.get("ip") or "Шлюз Amnezia"
                else:
                    pix = get_openconnect_pixmap(16, 16)
                    if not pix.isNull():
                        lbl_icon.setPixmap(pix)
                    else:
                        lbl_icon.setText("🛡")
                    proto_label = "<span style='color: #22d3ee; font-weight: 700;'>OpenConnect</span>"
                    host = conn.get("host") or conn.get("server") or ""
                    port = conn.get("port", 443)
                    desc = f"{host}:{port}" if host else "Шлюз OpenConnect"

                r_layout.addWidget(lbl_icon)

                lbl_info = QLabel(f"<b>{c_name}</b> ({proto_label}) — <span style='color: #94a3b8;'>{desc}</span>")
                lbl_info.setTextFormat(Qt.RichText)
                lbl_info.setWordWrap(True)
                lbl_info.setToolTip(f"{c_name} — {desc}")
                lbl_info.setStyleSheet("font-size: 12px; color: #f1f5f9; background: transparent; border: none;")
                r_layout.addWidget(lbl_info, 1)

                self.sub_conn_layout.addWidget(row_frame)

        self.sub_conn_container.setVisible(True)

    def _show_sub_error(self, err_text: str):
        self.lbl_sub_status_badge.setText("⚠ Ошибка загрузки")
        self.lbl_sub_status_badge.setStyleSheet("""
            color: #f87171;
            background-color: rgba(239, 68, 68, 0.12);
            border: 1px solid rgba(239, 68, 68, 0.35);
            border-radius: 12px;
            padding: 4px 12px;
            font-weight: 700;
            font-size: 11px;
        """)
        self.lbl_sub_error.setText(f"⚠ {err_text}")
        self.lbl_sub_error.setVisible(True)
        self.lbl_sub_user_info.setVisible(False)
        self.lbl_sub_conn_title.setVisible(False)
        self.sub_conn_container.setVisible(False)

    def _browse_conf_file(self):
        initial_dir = os.path.dirname(self.input_awg_path.text()) if self.input_awg_path.text() else ""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Импортировать файл конфигурации AmneziaWG",
            initial_dir,
            "Конфигурации WireGuard/Amnezia (*.conf);;Все файлы (*.*)"
        )
        if path and os.path.isfile(path):
            self.input_awg_path.setText(path)
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read().strip()
                self.text_awg_config.setPlainText(content)

                if not self.input_name.text().strip() or not getattr(self, "_name_user_customized", False):
                    base = os.path.splitext(os.path.basename(path))[0]
                    self.input_name.setText(base)

                self._update_awg_preview()
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось прочитать файл конфигурации:\n{e}")

    def _on_name_text_edited(self, text: str):
        self._name_user_customized = bool(text.strip())

    def _on_oc_user_text_changed(self, text: str):
        if self.combo_proto.currentData() == "openconnect":
            if not getattr(self, "_name_user_customized", False):
                self.input_name.setText(text.strip())

    def _on_awg_text_changed(self):
        self._update_awg_preview()

    def _update_awg_preview(self):
        content = self.text_awg_config.toPlainText().strip()
        if not content:
            self.lbl_awg_status.setText("○ Конфигурация не загружена (вставьте текст или выберите файл)")
            self.lbl_awg_status.setStyleSheet("font-size: 11px; color: #94a3b8; font-weight: 600;")
            return

        try:
            parsed = AmneziaWGLauncher.parse_config_text(content)
            ep = parsed.get("endpoint") or "Не указан"
            addr = parsed.get("address") or "Не указан"
            obf = "Да" if parsed.get("obfuscation") else "Стандартный WG"
            self.lbl_awg_status.setText(f"✔ Шлюз: {ep} • IP: {addr} • Обфускация: {obf}")
            self.lbl_awg_status.setStyleSheet("font-size: 11px; color: #34d399; font-weight: 700;")
        except Exception:
            self.lbl_awg_status.setText("⚠ Ошибка парсинга параметров .conf")
            self.lbl_awg_status.setStyleSheet("font-size: 11px; color: #fbbf24; font-weight: 700;")

    def _toggle_pwd_visibility(self):
        if self.input_oc_pwd.echoMode() == QLineEdit.Password:
            self.input_oc_pwd.setEchoMode(QLineEdit.Normal)
            self.btn_toggle_pwd.setText("Скрыть")
        else:
            self.input_oc_pwd.setEchoMode(QLineEdit.Password)
            self.btn_toggle_pwd.setText("Показать")

    def _on_proto_changed(self, index: int):
        self.stack.setCurrentIndex(index)
        proto = self.combo_proto.currentData()

        if proto == "subscription":
            if hasattr(self, "base_form"):
                if hasattr(self.base_form, "setRowVisible"):
                    self.base_form.setRowVisible(self.input_name, False)
                else:
                    self.input_name.setVisible(False)
                    lbl = self.base_form.labelForField(self.input_name)
                    if lbl:
                        lbl.setVisible(False)
            self.btn_save.setText("📥  Сохранить подписку")
            return

        if hasattr(self, "base_form"):
            if hasattr(self.base_form, "setRowVisible"):
                self.base_form.setRowVisible(self.input_name, True)
            else:
                self.input_name.setVisible(True)
                lbl = self.base_form.labelForField(self.input_name)
                if lbl:
                    lbl.setVisible(True)

        self.btn_save.setText("💾  Сохранить подключение" if self.is_edit else "+  Сохранить подключение")

        if proto == "openconnect":
            if not getattr(self, "_name_user_customized", False):
                user = self.input_oc_user.text().strip()
                if user:
                    self.input_name.setText(user)
        elif proto == "amnezia":
            if not getattr(self, "_name_user_customized", False):
                cfg_path = self.input_awg_path.text().strip()
                if cfg_path:
                    self.input_name.setText(os.path.splitext(os.path.basename(cfg_path))[0])

    def _load_existing_data(self):
        proto = self.profile.get("proto", "amnezia")
        idx = 0 if proto == "amnezia" else 1
        self.combo_proto.setCurrentIndex(idx)
        self.combo_proto.setEnabled(False)  # Запрет смены типа у созданного профиля

        self.input_name.setText(self.profile.get("name", ""))

        if proto == "amnezia":
            self.input_awg_path.setText(self.profile.get("config_path", ""))
            self.input_awg_iface.setText(self.profile.get("interface", "bobr0"))
            raw_content = self.profile.get("config_content", "")
            if raw_content:
                self.text_awg_config.setPlainText(raw_content)
            elif self.profile.get("config_path") and os.path.isfile(self.profile.get("config_path")):
                try:
                    with open(self.profile.get("config_path"), "r", encoding="utf-8", errors="ignore") as f:
                        self.text_awg_config.setPlainText(f.read().strip())
                except Exception:
                    pass
            self._update_awg_preview()
        else:
            self.input_oc_server.setText(self.profile.get("server", ""))
            self.spin_oc_port.setValue(int(self.profile.get("port", 443)))
            self.input_oc_cam.setText(self.profile.get("camouflage", ""))
            self.input_oc_user.setText(self.profile.get("username", ""))

            saved_pwd = self.profile.get("password", "")
            if not saved_pwd:
                saved_pwd = settings.get_password("openconnect_password")
            self.input_oc_pwd.setText(saved_pwd)
            self.cb_remember_pwd.setChecked(self.profile.get("remember_password", True))

    def _on_save_clicked(self):
        proto = self.combo_proto.currentData()

        if proto == "subscription":
            url = self.input_sub_url.text().strip()
            if not url:
                QMessageBox.warning(self, "Внимание", "Пожалуйста, укажите ссылку на подписку.")
                self.input_sub_url.setFocus()
                return

            self.btn_save.setEnabled(False)
            self.btn_save.setText("⏳ Сохранение...")
            QApplication.processEvents()

            try:
                ok, msg, profiles = SubscriptionManager.sync(url)
                if ok:
                    self.is_subscription_synced = True
                    self.synced_profiles_count = len(profiles)
                    self.accept()
                else:
                    QMessageBox.warning(self, "Ошибка синхронизации", msg)
            except Exception as e:
                QMessageBox.warning(self, "Ошибка синхронизации", f"Не удалось обновить подписку:\n{e}")
            finally:
                self.btn_save.setEnabled(True)
                self.btn_save.setText("📥  Сохранить подписку")
            return

        name = self.input_name.text().strip()

        # Если поле названия подключения пустое, автоматически берём логин для OpenConnect или имя .conf для Amnezia
        if not name:
            if proto == "openconnect":
                user = self.input_oc_user.text().strip()
                if user:
                    name = user
                    self.input_name.setText(name)
            elif proto == "amnezia":
                cfg_path = self.input_awg_path.text().strip()
                if cfg_path:
                    name = os.path.splitext(os.path.basename(cfg_path))[0]
                    self.input_name.setText(name)

        if not name:
            if proto == "openconnect":
                QMessageBox.warning(self, "Внимание", "Пожалуйста, укажите логин или название подключения.")
                if not self.input_oc_user.text().strip():
                    self.input_oc_user.setFocus()
                else:
                    self.input_name.setFocus()
            else:
                QMessageBox.warning(self, "Внимание", "Пожалуйста, укажите название подключения.")
                self.input_name.setFocus()
            return

        self.profile["name"] = name
        self.profile["proto"] = proto

        if proto == "amnezia":
            config_content = self.text_awg_config.toPlainText().strip()
            cfg_path = self.input_awg_path.text().strip()

            if not config_content and cfg_path and os.path.isfile(cfg_path):
                try:
                    with open(cfg_path, "r", encoding="utf-8", errors="ignore") as f:
                        config_content = f.read().strip()
                except Exception:
                    pass

            if not config_content:
                QMessageBox.warning(
                    self,
                    "Внимание",
                    "Пожалуйста, импортируйте .conf файл или вставьте параметры конфигурации AmneziaWG."
                )
                return

            self.profile["config_content"] = config_content
            self.profile["config_path"] = cfg_path
            self.profile["interface"] = self.input_awg_iface.text().strip() or "bobr0"

            # Сразу парсим и сохраняем параметры шлюза
            try:
                parsed = AmneziaWGLauncher.parse_config_text(config_content)
                self.profile["endpoint"] = parsed.get("endpoint", "")
                self.profile["address"] = parsed.get("address", "")
                self.profile["dns"] = parsed.get("dns", "")
                self.profile["allowed_ips"] = parsed.get("allowed_ips", "")
                self.profile["obfuscation"] = parsed.get("obfuscation", {})
            except Exception:
                pass

        else:
            server = self.input_oc_server.text().strip()
            if not server:
                QMessageBox.warning(self, "Внимание", "Пожалуйста, укажите адрес сервера OpenConnect.")
                return
            self.profile["server"] = server
            self.profile["port"] = self.spin_oc_port.value()
            self.profile["protocol"] = "anyconnect"
            self.profile["camouflage"] = self.input_oc_cam.text().strip()
            self.profile["username"] = self.input_oc_user.text().strip()
            self.profile["remember_password"] = self.cb_remember_pwd.isChecked()

            pwd = self.input_oc_pwd.text()
            if self.cb_remember_pwd.isChecked():
                self.profile["password"] = pwd
                if pwd:
                    settings.set_password(pwd, "openconnect_password")
            else:
                self.profile["password"] = ""
                settings.set_password("", "openconnect_password")

        self.accept()

    def get_data(self) -> Dict[str, Any]:
        return self.profile
