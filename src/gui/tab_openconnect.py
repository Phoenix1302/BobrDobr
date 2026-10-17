from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QSpinBox, QCheckBox, QGroupBox, QGridLayout, QMessageBox
)
from PySide6.QtCore import Qt
from core.openconnect import OpenConnectLauncher
from core.vpn_manager import VPNState
from utils.config_store import settings


class OpenConnectTab(QWidget):
    """
    Вкладка OpenConnect в стиле гидроинженерии БобрДобр.
    Настройка транзитного шлюза, протоколов AnyConnect/Pulse/GP,
    безопасная передача пароля через stdin и сохранение параметров между запусками.
    """

    def __init__(self, launcher: OpenConnectLauncher, parent=None):
        super().__init__(parent)
        self.launcher = launcher
        self._init_ui()
        self._restore_saved_state()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(14, 14, 14, 14)

        # 1. Речной шлюз и протокол
        server_group = QGroupBox("Речной шлюз и протокол соединения")
        server_layout = QGridLayout(server_group)
        server_layout.setSpacing(10)

        server_layout.addWidget(QLabel("Адрес плотины / Шлюз:"), 0, 0)
        self.server_input = QLineEdit()
        self.server_input.setPlaceholderText("dam.oredezh-river.net или 192.168.1.1")
        self.server_input.textChanged.connect(lambda t: settings.set("openconnect_server", t.strip()))
        server_layout.addWidget(self.server_input, 0, 1, 1, 2)

        server_layout.addWidget(QLabel("Гидроствор (Порт):"), 1, 0)
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(443)
        self.port_spin.setMaximumWidth(120)
        self.port_spin.valueChanged.connect(lambda v: settings.set("openconnect_port", v))
        server_layout.addWidget(self.port_spin, 1, 1)

        server_layout.addWidget(QLabel("Тип шлюзовой камеры:"), 2, 0)
        self.protocol_combo = QComboBox()
        for proto_key, proto_desc in self.launcher.SUPPORTED_PROTOCOLS.items():
            self.protocol_combo.addItem(proto_desc, proto_key)
        self.protocol_combo.currentIndexChanged.connect(
            lambda: settings.set("openconnect_proto", self.protocol_combo.currentData())
        )
        server_layout.addWidget(self.protocol_combo, 2, 1, 1, 2)

        # 1.1 Маскировка трафика (Camouflage Secret для ocserv)
        self.camouflage_cb = QCheckBox("Маскировка шлюза (Camouflage):")
        self.camouflage_cb.setToolTip("Режим ocserv camouflage: передаёт секретный ключ в URL запроса для авторизации на шлюзе.")
        self.camouflage_cb.stateChanged.connect(self._on_camouflage_changed)
        server_layout.addWidget(self.camouflage_cb, 3, 0)

        self.camouflage_secret_input = QLineEdit()
        self.camouflage_secret_input.setPlaceholderText("Секретный ключ (например: secret_token)")
        self.camouflage_secret_input.setEnabled(False)
        self.camouflage_secret_input.textChanged.connect(
            lambda t: settings.set("openconnect_camouflage_secret", t.strip())
        )
        server_layout.addWidget(self.camouflage_secret_input, 3, 1, 1, 2)

        main_layout.addWidget(server_group)

        # 2. Авторизация на гидроузле
        auth_group = QGroupBox("Пропуск на гидроузел (Авторизация)")
        auth_layout = QGridLayout(auth_group)
        auth_layout.setSpacing(10)

        auth_layout.addWidget(QLabel("Позывной бобра (Логин):"), 0, 0)
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Главный_Гидротехник")
        self.username_input.textChanged.connect(lambda t: settings.set("openconnect_username", t.strip()))
        auth_layout.addWidget(self.username_input, 0, 1, 1, 2)

        auth_layout.addWidget(QLabel("Стук хвостом (Пароль):"), 1, 0)
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Передаётся строго в изолированный pipe")
        self.password_input.textChanged.connect(self._on_password_changed)
        auth_layout.addWidget(self.password_input, 1, 1)

        self.toggle_pwd_btn = QPushButton("Показать")
        self.toggle_pwd_btn.setObjectName("btn_secondary")
        self.toggle_pwd_btn.setFixedWidth(80)
        self.toggle_pwd_btn.clicked.connect(self._toggle_password_visibility)
        auth_layout.addWidget(self.toggle_pwd_btn, 1, 2)

        # Чекбоксы запоминания и сертификатов
        checkbox_layout = QHBoxLayout()
        self.remember_pwd_cb = QCheckBox("Запомнить пароль в профиле")
        self.remember_pwd_cb.stateChanged.connect(self._on_remember_changed)
        checkbox_layout.addWidget(self.remember_pwd_cb)

        self.insecure_cert_cb = QCheckBox("Игнорировать проверки сертификата")
        self.insecure_cert_cb.stateChanged.connect(
            lambda: settings.set("openconnect_insecure", self.insecure_cert_cb.isChecked())
        )
        checkbox_layout.addWidget(self.insecure_cert_cb)
        checkbox_layout.addStretch()

        auth_layout.addLayout(checkbox_layout, 2, 0, 1, 3)

        main_layout.addWidget(auth_group)

        main_layout.addStretch()

        # 3. Главная кнопка действия
        self.action_btn = QPushButton("Открыть гидрошлюз (OpenConnect)")
        self.action_btn.setObjectName("btn_connect")
        self.action_btn.setFixedHeight(48)
        self.action_btn.setCursor(Qt.PointingHandCursor)
        self.action_btn.clicked.connect(self._toggle_connection)
        main_layout.addWidget(self.action_btn)

    def _restore_saved_state(self):
        """Восстановление сохранённых параметров OpenConnect."""
        self.server_input.setText(settings.get("openconnect_server", ""))
        self.port_spin.setValue(settings.get("openconnect_port", 443))
        self.username_input.setText(settings.get("openconnect_username", ""))

        saved_proto = settings.get("openconnect_proto", "anyconnect")
        idx = self.protocol_combo.findData(saved_proto)
        if idx >= 0:
            self.protocol_combo.setCurrentIndex(idx)

        self.insecure_cert_cb.setChecked(settings.get("openconnect_insecure", False))

        cam_enabled = settings.get("openconnect_camouflage", False)
        self.camouflage_cb.setChecked(cam_enabled)
        self.camouflage_secret_input.setEnabled(cam_enabled)
        self.camouflage_secret_input.setText(settings.get("openconnect_camouflage_secret", ""))

        remember = settings.get("openconnect_remember_pwd", False)
        self.remember_pwd_cb.setChecked(remember)
        if remember:
            self.password_input.setText(settings.get_password("openconnect_password"))

    def _on_camouflage_changed(self):
        checked = self.camouflage_cb.isChecked()
        self.camouflage_secret_input.setEnabled(checked)
        settings.set("openconnect_camouflage", checked)

    def _on_password_changed(self):
        if self.remember_pwd_cb.isChecked():
            settings.set_password(self.password_input.text(), "openconnect_password")

    def _on_remember_changed(self):
        checked = self.remember_pwd_cb.isChecked()
        settings.set("openconnect_remember_pwd", checked)
        if checked:
            settings.set_password(self.password_input.text(), "openconnect_password")
        else:
            settings.set_password("", "openconnect_password")

    def _toggle_password_visibility(self):
        if self.password_input.echoMode() == QLineEdit.Password:
            self.password_input.setEchoMode(QLineEdit.Normal)
            self.toggle_pwd_btn.setText("Скрыть")
        else:
            self.password_input.setEchoMode(QLineEdit.Password)
            self.toggle_pwd_btn.setText("Показать")

    def _toggle_connection(self):
        if self.launcher.is_running():
            self.launcher.stop_connection()
        else:
            server = self.server_input.text().strip()
            if not server:
                QMessageBox.warning(self, "Адрес не указан", "Пожалуйста, введите адрес гидроузла!")
                return

            from utils.platform_helper import is_admin, is_windows
            if is_windows() and not is_admin():
                QMessageBox.warning(
                    self,
                    "Требуются права Администратора",
                    "Для управления гидрошлюзом и настройки сетевой маршрутизации требуются права Администратора.\n\n"
                    "Пожалуйста, запустите приложение от имени Администратора (ПКМ → Запуск от имени администратора).",
                    QMessageBox.Ok
                )
                return

            proto = self.protocol_combo.currentData()
            port = self.port_spin.value()
            username = self.username_input.text().strip()
            password = self.password_input.text()
            allow_insecure = self.insecure_cert_cb.isChecked()
            cam_secret = self.camouflage_secret_input.text().strip() if self.camouflage_cb.isChecked() else ""

            self.launcher.start_connection(
                server=server,
                port=port,
                username=username,
                password=password,
                protocol=proto,
                allow_insecure_cert=allow_insecure,
                camouflage_secret=cam_secret
            )

    def update_ui_state(self, state: str):
        """Обновление интерфейса в зависимости от состояния шлюза."""
        if state == VPNState.CONNECTED.value:
            self.action_btn.setText("Перекрыть гидрошлюз (Отключить)")
            self.action_btn.setObjectName("btn_disconnect")
            self.action_btn.setEnabled(True)
            self._set_inputs_enabled(False)
        elif state == VPNState.CONNECTING.value:
            self.action_btn.setText("Продувка шлюзовых камер...")
            self.action_btn.setEnabled(False)
        elif state == VPNState.DISCONNECTING.value:
            self.action_btn.setText("Закрытие затворов шлюза...")
            self.action_btn.setEnabled(False)
        else:
            self.action_btn.setText("Открыть гидрошлюз (OpenConnect)")
            self.action_btn.setObjectName("btn_connect")
            self.action_btn.setEnabled(True)
            self._set_inputs_enabled(True)

        self.action_btn.style().unpolish(self.action_btn)
        self.action_btn.style().polish(self.action_btn)

    def _set_inputs_enabled(self, enabled: bool):
        self.server_input.setEnabled(enabled)
        self.port_spin.setEnabled(enabled)
        self.protocol_combo.setEnabled(enabled)
        self.camouflage_cb.setEnabled(enabled)
        self.camouflage_secret_input.setEnabled(enabled and self.camouflage_cb.isChecked())
        self.username_input.setEnabled(enabled)
        self.password_input.setEnabled(enabled)
        self.insecure_cert_cb.setEnabled(enabled)
        self.remember_pwd_cb.setEnabled(enabled)

