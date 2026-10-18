import os
from typing import Dict, Any, Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QSpinBox, QCheckBox,
    QFileDialog, QGroupBox, QStackedWidget, QWidget, QMessageBox,
    QPlainTextEdit, QSizePolicy, QListView, QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer
from core.amnezia import AmneziaWGLauncher
from utils.config_store import settings
from utils.platform_helper import get_base_dir
from gui.styles import get_amnezia_icon, get_openconnect_icon


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

        title = "Настройка подключения" if self.is_edit else "Создать новое подключение"
        self.setWindowTitle(title)
        self.resize(620, 700)
        self.setMinimumSize(580, 640)
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
        if not amz_icon.isNull():
            self.combo_proto.addItem(amz_icon, "  AmneziaWG", "amnezia")
        else:
            self.combo_proto.addItem("⚡  AmneziaWG", "amnezia")
        if not oc_icon.isNull():
            self.combo_proto.addItem(oc_icon, "  OpenConnect", "openconnect")
        else:
            self.combo_proto.addItem("🔒  OpenConnect", "openconnect")
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

        root_layout.addWidget(self.stack, 1)

        # 3. Кнопки сохранения и отмены
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 8, 0, 0)
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
        self.input_awg_path.setFixedHeight(36)
        self.input_awg_path.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.input_awg_path.setPlaceholderText("Импортировать .conf файл конфигурации...")
        file_row.addWidget(self.input_awg_path, 1)

        btn_browse = QPushButton("Обзор...")
        btn_browse.setObjectName("btn_secondary")
        btn_browse.setCursor(Qt.PointingHandCursor)
        btn_browse.setFixedHeight(36)
        btn_browse.setFixedWidth(92)
        btn_browse.clicked.connect(self._browse_conf_file)
        file_row.addWidget(btn_browse, 0)
        form.addRow("Импорт из файла:", file_row)

        self.input_awg_iface = QLineEdit("awg0")
        self.input_awg_iface.setFixedHeight(36)
        self.input_awg_iface.setPlaceholderText("awg0")
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
            self.input_awg_iface.setText(self.profile.get("interface", "awg0"))
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
            self.profile["interface"] = self.input_awg_iface.text().strip() or "awg0"

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
