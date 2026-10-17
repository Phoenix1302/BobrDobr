import os
from typing import Optional, Dict
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QGroupBox, QGridLayout, QMessageBox
)
from PySide6.QtCore import Qt
from core.amnezia import AmneziaWGLauncher
from core.vpn_manager import VPNState
from utils.config_store import settings


class AmneziaTab(QWidget):
    """
    Вкладка AmneziaWG в стиле гидроинженерии БобрДобр.
    Импорт спецификации плотины (.conf), мониторинг шлюза,
    сохранение настроек между запусками и адаптивная сетка параметров обфускации.
    """

    def __init__(self, launcher: AmneziaWGLauncher, parent=None):
        super().__init__(parent)
        self.launcher = launcher
        self._obfuscation_inputs: Dict[str, QLineEdit] = {}
        self._init_ui()
        self.setAcceptDrops(True)
        self._restore_saved_state()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(14, 14, 14, 14)

        # 1. Чертёж плотины (.conf)
        config_group = QGroupBox("Чертёж плотины (.conf)")
        config_layout = QHBoxLayout(config_group)
        config_layout.setSpacing(8)

        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Перетащите файл .conf сюда или укажите путь к чертежу...")
        self.path_input.textChanged.connect(self._on_path_changed)
        config_layout.addWidget(self.path_input)

        self.browse_btn = QPushButton("Обзор...")
        self.browse_btn.setObjectName("btn_secondary")
        self.browse_btn.setFixedWidth(90)
        self.browse_btn.clicked.connect(self._browse_file)
        config_layout.addWidget(self.browse_btn)

        main_layout.addWidget(config_group)

        # 2. Параметры гидроузла
        details_group = QGroupBox("Параметры гидроузла")
        details_layout = QGridLayout(details_group)
        details_layout.setSpacing(8)

        self.lbl_endpoint = QLabel("—")
        self.lbl_endpoint.setStyleSheet("color: #d97706; font-weight: bold;")
        self.lbl_address = QLabel("—")
        self.lbl_allowed_ips = QLabel("—")

        details_layout.addWidget(QLabel("Основной гидроузел (Endpoint):"), 0, 0)
        details_layout.addWidget(self.lbl_endpoint, 0, 1)
        details_layout.addWidget(QLabel("Внутренний приток (Client IP):"), 1, 0)
        details_layout.addWidget(self.lbl_address, 1, 1)
        details_layout.addWidget(QLabel("Зона затопления (Allowed IPs):"), 2, 0)
        details_layout.addWidget(self.lbl_allowed_ips, 2, 1)

        main_layout.addWidget(details_group)

        # 3. Гидродинамическая маскировка (Защита плотины от лесонадзора / DPI)
        obf_group = QGroupBox("Гидродинамическая маскировка (Защита плотины от лесонадзора / DPI)")
        obf_layout = QGridLayout(obf_group)
        obf_layout.setHorizontalSpacing(14)
        obf_layout.setVerticalSpacing(10)

        # Ряд 1: Jc, Jmin, Jmax, S1, S2
        row1_items = [
            ("Jc (Брёвна)", "Jc", 0),
            ("Jmin (Мин. B)", "Jmin", 1),
            ("Jmax (Макс. B)", "Jmax", 2),
            ("S1 (Инит, B)", "S1", 3),
            ("S2 (Ответ, B)", "S2", 4),
        ]
        for label_text, key, col in row1_items:
            cell = QVBoxLayout()
            cell.setSpacing(3)
            lbl = QLabel(label_text)
            lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
            inp = QLineEdit()
            inp.setAlignment(Qt.AlignCenter)
            inp.textChanged.connect(self._on_obfuscation_changed)
            self._obfuscation_inputs[key] = inp
            cell.addWidget(lbl)
            cell.addWidget(inp)
            obf_layout.addLayout(cell, 0, col)

        # Ряд 2: Магические заголовки H1 - H4
        row2_items = [
            ("H1 (Метка #1)", "H1", 0),
            ("H2 (Метка #2)", "H2", 1),
            ("H3 (Метка #3)", "H3", 2),
            ("H4 (Метка #4)", "H4", 3),
        ]
        for label_text, key, col in row2_items:
            cell = QVBoxLayout()
            cell.setSpacing(3)
            lbl = QLabel(label_text)
            lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
            inp = QLineEdit()
            inp.setAlignment(Qt.AlignCenter)
            inp.textChanged.connect(self._on_obfuscation_changed)
            self._obfuscation_inputs[key] = inp
            cell.addWidget(lbl)
            cell.addWidget(inp)
            obf_layout.addLayout(cell, 1, col)

        main_layout.addWidget(obf_group)

        main_layout.addStretch()

        # 4. Главная кнопка действия (без ломающихся эмодзи)
        self.action_btn = QPushButton("Возвести плотину (AmneziaWG)")
        self.action_btn.setObjectName("btn_connect")
        self.action_btn.setFixedHeight(48)
        self.action_btn.setCursor(Qt.PointingHandCursor)
        self.action_btn.clicked.connect(self._toggle_connection)
        main_layout.addWidget(self.action_btn)

    def _browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите чертёж плотины AmneziaWG",
            "",
            "Конфиг плотины (*.conf);;Все файлы (*.*)"
        )
        if file_path:
            self._load_config(file_path)

    def _load_config(self, file_path: str):
        self.path_input.setText(file_path)
        settings.set("amnezia_conf_path", file_path)
        try:
            parsed = self.launcher.parse_config(file_path)
            self.lbl_endpoint.setText(parsed["peer"].get("Endpoint", "Не указан"))
            self.lbl_address.setText(parsed["interface"].get("Address", "Не указан"))
            self.lbl_allowed_ips.setText(parsed["peer"].get("AllowedIPs", "0.0.0.0/0, ::/0"))

            obf = parsed["obfuscation"]
            for key, input_widget in self._obfuscation_inputs.items():
                input_widget.setText(obf.get(key, ""))

            self._save_obfuscation_settings()

        except Exception as e:
            QMessageBox.warning(self, "Ошибка чертежа", f"Не удалось разобрать конфигурацию: {e}")

    def _on_path_changed(self, text: str):
        clean_text = text.strip()
        settings.set("amnezia_conf_path", clean_text)
        if clean_text and os.path.isfile(clean_text) and clean_text != self.launcher.config_path:
            try:
                parsed = self.launcher.parse_config(clean_text)
                self.lbl_endpoint.setText(parsed["peer"].get("Endpoint", "Не указан"))
                self.lbl_address.setText(parsed["interface"].get("Address", "Не указан"))
                self.lbl_allowed_ips.setText(parsed["peer"].get("AllowedIPs", "0.0.0.0/0, ::/0"))
                for key, input_widget in self._obfuscation_inputs.items():
                    if not input_widget.text():
                        input_widget.setText(parsed["obfuscation"].get(key, ""))
            except Exception:
                pass

    def _on_obfuscation_changed(self):
        self._save_obfuscation_settings()

    def _save_obfuscation_settings(self):
        overrides = {k: v.text().strip() for k, v in self._obfuscation_inputs.items() if v.text().strip()}
        settings.set("amnezia_obfuscation", overrides)

    def _restore_saved_state(self):
        """Восстановление сохранённых настроек при запуске."""
        saved_path = settings.get("amnezia_conf_path", "")
        if saved_path:
            self.path_input.setText(saved_path)
            if os.path.isfile(saved_path):
                try:
                    parsed = self.launcher.parse_config(saved_path)
                    self.lbl_endpoint.setText(parsed["peer"].get("Endpoint", "Не указан"))
                    self.lbl_address.setText(parsed["interface"].get("Address", "Не указан"))
                    self.lbl_allowed_ips.setText(parsed["peer"].get("AllowedIPs", "0.0.0.0/0, ::/0"))
                    for key, input_widget in self._obfuscation_inputs.items():
                        input_widget.setText(parsed["obfuscation"].get(key, ""))
                except Exception:
                    pass

        # Применяем сохранённые ручные оверрайды если были
        saved_obf = settings.get("amnezia_obfuscation", {})
        if isinstance(saved_obf, dict):
            for key, val in saved_obf.items():
                if key in self._obfuscation_inputs and val:
                    self._obfuscation_inputs[key].setText(str(val))

    def _toggle_connection(self):
        if self.launcher.is_running():
            self.launcher.stop_connection()
        else:
            config_file = self.path_input.text().strip()
            if not config_file or not os.path.isfile(config_file):
                QMessageBox.warning(self, "Чертёж не найден", "Пожалуйста, выберите валидный файл плотины .conf!")
                return

            from utils.platform_helper import is_admin, is_windows
            if is_windows() and not is_admin():
                QMessageBox.warning(
                    self,
                    "Требуются права Администратора",
                    "Для возведения плотины (создания виртуального сетевого Wintun-адаптера) требуются права Администратора.\n\n"
                    "Пожалуйста, запустите приложение от имени Администратора (ПКМ → Запуск от имени администратора).",
                    QMessageBox.Ok
                )
                return

            overrides = {k: v.text().strip() for k, v in self._obfuscation_inputs.items() if v.text().strip()}
            self.launcher.start_connection(
                config_path=config_file,
                obfuscation_overrides=overrides if overrides else None
            )

    def update_ui_state(self, state: str):
        """Обновление интерфейса в зависимости от фазы плотины."""
        if state == VPNState.CONNECTED.value:
            self.action_btn.setText("Разобрать завал (Отключить)")
            self.action_btn.setObjectName("btn_disconnect")
            self.action_btn.setEnabled(True)
            self._set_inputs_enabled(False)
        elif state == VPNState.CONNECTING.value:
            self.action_btn.setText("Сплав леса и возведение плотины...")
            self.action_btn.setEnabled(False)
        elif state == VPNState.DISCONNECTING.value:
            self.action_btn.setText("Спуск воды из гидроузла...")
            self.action_btn.setEnabled(False)
        else:
            self.action_btn.setText("Возвести плотину (AmneziaWG)")
            self.action_btn.setObjectName("btn_connect")
            self.action_btn.setEnabled(True)
            self._set_inputs_enabled(True)

        self.action_btn.style().unpolish(self.action_btn)
        self.action_btn.style().polish(self.action_btn)

    def _set_inputs_enabled(self, enabled: bool):
        self.path_input.setEnabled(enabled)
        self.browse_btn.setEnabled(enabled)
        for inp in self._obfuscation_inputs.values():
            inp.setEnabled(enabled)

    # Drag and Drop поддержка
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path.endswith(".conf") or os.path.isfile(path):
                self._load_config(path)
