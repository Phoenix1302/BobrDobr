import os
from typing import Dict, Any, Optional
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QWidget,
    QGraphicsDropShadowEffect
)
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt, Signal
from core.vpn_manager import VPNState


CONNECT_BTN_STYLE = """
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #10b981, stop:1 #059669);
    color: #ffffff;
    font-size: 13px;
    font-weight: 700;
    padding: 7px 22px;
    border-radius: 8px;
    border: 1px solid rgba(255, 255, 255, 0.16);
    border-bottom: 2px solid #047857;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #34d399, stop:1 #10b981);
    color: #ffffff;
    border: 1px solid rgba(255, 255, 255, 0.28);
    border-bottom: 2px solid #065f46;
}
QPushButton:pressed {
    background-color: #047857;
    border: 1px solid #047857;
}
"""

DISCONNECT_BTN_STYLE = """
QPushButton {
    background-color: rgba(239, 68, 68, 0.12);
    color: #fca5a5;
    font-size: 13px;
    font-weight: 700;
    padding: 7px 22px;
    border-radius: 8px;
    border: 1px solid rgba(239, 68, 68, 0.45);
}
QPushButton:hover {
    background-color: rgba(239, 68, 68, 0.28);
    border: 1px solid #ef4444;
    color: #ffffff;
}
QPushButton:pressed {
    background-color: rgba(185, 28, 28, 0.55);
    border: 1px solid #dc2626;
    color: #ffffff;
}
"""

CONNECTING_BTN_STYLE = """
QPushButton {
    background-color: rgba(217, 119, 6, 0.14);
    color: #fbbf24;
    font-weight: 700;
    font-size: 13px;
    border-radius: 8px;
    border: 1px solid rgba(217, 119, 6, 0.45);
    padding: 7px 22px;
}
"""

CARD_STYLE_DISCONNECTED = """
QFrame#vpn_profile_card {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #18232a, stop:1 #0f161a);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-top: 1px solid rgba(255, 255, 255, 0.18);
    border-radius: 12px;
}
QFrame#vpn_profile_card:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1e2c35, stop:1 #131c21);
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-top: 1px solid rgba(255, 255, 255, 0.28);
    border-radius: 12px;
}
"""

CARD_STYLE_CONNECTED = """
QFrame#vpn_profile_card {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #18232a, stop:1 #0f161a);
    border: 1px solid rgba(16, 185, 129, 0.50);
    border-top: 1px solid rgba(52, 211, 153, 0.85);
    border-radius: 12px;
}
QFrame#vpn_profile_card:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1e2c35, stop:1 #131c21);
    border: 1px solid rgba(16, 185, 129, 0.70);
    border-top: 1px solid rgba(52, 211, 153, 1.0);
    border-radius: 12px;
}
"""

CARD_STYLE_CONNECTING = """
QFrame#vpn_profile_card {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #18232a, stop:1 #0f161a);
    border: 1px solid rgba(245, 158, 11, 0.50);
    border-top: 1px solid rgba(251, 191, 36, 0.85);
    border-radius: 12px;
}
QFrame#vpn_profile_card:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1e2c35, stop:1 #131c21);
    border: 1px solid rgba(245, 158, 11, 0.70);
    border-top: 1px solid rgba(251, 191, 36, 1.0);
    border-radius: 12px;
}
"""

CARD_STYLE_ERROR = """
QFrame#vpn_profile_card {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #18232a, stop:1 #0f161a);
    border: 1px solid rgba(239, 68, 68, 0.50);
    border-top: 1px solid rgba(248, 113, 113, 0.85);
    border-radius: 12px;
}
QFrame#vpn_profile_card:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1e2c35, stop:1 #131c21);
    border: 1px solid rgba(239, 68, 68, 0.70);
    border-top: 1px solid rgba(248, 113, 113, 1.0);
    border-radius: 12px;
}
"""


class VPNProfileCard(QFrame):
    """
    Карточка подключения в едином списке профилей BobrDobr VPN.
    Поддерживает протоколы AmneziaWG и OpenConnect в едином визуальном стиле
    с объёмным эффектом парения и адаптивной контурной подсветкой состояния.
    """
    connect_requested = Signal(str)
    disconnect_requested = Signal(str)
    edit_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, profile: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.profile = profile
        self.profile_id = profile.get("id", "")
        self.proto = profile.get("proto", "amnezia")
        self.current_state = VPNState.DISCONNECTED

        self.setObjectName("vpn_profile_card")
        self.setProperty("proto", self.proto)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFrameShape(QFrame.StyledPanel)

        # Парящая контурная тень (Volumetric Floating Aura)
        self.shadow_effect = QGraphicsDropShadowEffect(self)
        self.shadow_effect.setXOffset(0)
        self.shadow_effect.setYOffset(3)
        self.shadow_effect.setBlurRadius(16)
        self.shadow_effect.setColor(QColor(0, 0, 0, 120))
        self.setGraphicsEffect(self.shadow_effect)

        self._init_ui()
        self.update_state(VPNState.DISCONNECTED)

    def enterEvent(self, event):
        super().enterEvent(event)
        self._apply_shadow(hover=True)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._apply_shadow(hover=False)

    def _apply_shadow(self, hover: bool = False):
        if not hasattr(self, "shadow_effect"):
            return

        if self.current_state == VPNState.CONNECTED:
            # Изумрудная рамка-тень активного подключения
            if hover:
                self.shadow_effect.setColor(QColor(16, 185, 129, 90))
                self.shadow_effect.setBlurRadius(24)
                self.shadow_effect.setYOffset(4)
            else:
                self.shadow_effect.setColor(QColor(16, 185, 129, 60))
                self.shadow_effect.setBlurRadius(18)
                self.shadow_effect.setYOffset(3)
        elif self.current_state in (VPNState.CONNECTING, VPNState.DISCONNECTING):
            # Янтарная рамка-тень подключения
            if hover:
                self.shadow_effect.setColor(QColor(245, 158, 11, 95))
                self.shadow_effect.setBlurRadius(24)
                self.shadow_effect.setYOffset(4)
            else:
                self.shadow_effect.setColor(QColor(245, 158, 11, 65))
                self.shadow_effect.setBlurRadius(18)
                self.shadow_effect.setYOffset(3)
        elif self.current_state == VPNState.ERROR:
            # Рубиновая рамка-тень ошибки
            if hover:
                self.shadow_effect.setColor(QColor(239, 68, 68, 90))
                self.shadow_effect.setBlurRadius(24)
                self.shadow_effect.setYOffset(4)
            else:
                self.shadow_effect.setColor(QColor(239, 68, 68, 60))
                self.shadow_effect.setBlurRadius(18)
                self.shadow_effect.setYOffset(3)
        else:
            # Не активно: глубокая тень парящей карточки
            if hover:
                self.shadow_effect.setColor(QColor(0, 0, 0, 160))
                self.shadow_effect.setBlurRadius(22)
                self.shadow_effect.setYOffset(5)
            else:
                self.shadow_effect.setColor(QColor(0, 0, 0, 120))
                self.shadow_effect.setBlurRadius(16)
                self.shadow_effect.setYOffset(3)

    def _init_ui(self):
        card_layout = QVBoxLayout(self)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(12)

        # 1. Верхний ряд: Бейдж протокола, Название, Статус и Главная кнопка
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        # Бейдж типа протокола
        proto_badge = QLabel()
        if self.proto == "amnezia":
            proto_badge.setText("⚡ AmneziaWG")
            proto_badge.setStyleSheet("""
                background-color: rgba(56, 189, 248, 0.12);
                color: #38bdf8;
                border: 1px solid rgba(56, 189, 248, 0.35);
                border-radius: 6px;
                padding: 3px 8px;
                font-size: 11px;
                font-weight: 800;
            """)
        else:
            proto_badge.setText("🔒 OpenConnect")
            proto_badge.setStyleSheet("""
                background-color: rgba(52, 211, 153, 0.12);
                color: #34d399;
                border: 1px solid rgba(52, 211, 153, 0.35);
                border-radius: 6px;
                padding: 3px 8px;
                font-size: 11px;
                font-weight: 800;
            """)
        top_row.addWidget(proto_badge)

        # Название профиля
        name_text = self.profile.get("name", "Без названия")
        self.lbl_name = QLabel(name_text)
        self.lbl_name.setStyleSheet("font-size: 16px; font-weight: 800; color: #f8fafc; margin-left: 2px;")
        top_row.addWidget(self.lbl_name)

        top_row.addStretch()

        # Бейдж статуса
        self.lbl_status = QLabel("○ Отключено")
        self.lbl_status.setStyleSheet("font-size: 11px; font-weight: 700; color: #94a3b8; padding: 4px 10px;")
        top_row.addWidget(self.lbl_status)

        # Главная кнопка действия (Подключить / Отключить)
        self.btn_toggle = QPushButton("Подключить")
        self.btn_toggle.setObjectName("btn_connect")
        self.btn_toggle.setCursor(Qt.PointingHandCursor)
        self.btn_toggle.setMinimumWidth(150)
        self.btn_toggle.setFixedHeight(34)
        self.btn_toggle.clicked.connect(self._on_toggle_clicked)
        top_row.addWidget(self.btn_toggle)

        card_layout.addLayout(top_row)

        # 2. Средний ряд: Детали соединения (Шлюз, Конфиг, Маскировка)
        details_row = QHBoxLayout()
        details_row.setSpacing(12)

        if self.proto == "amnezia":
            ep = self.profile.get("endpoint", "")
            addr = self.profile.get("address", "")
            iface = self.profile.get("interface", "awg0")
            cfg_path = self.profile.get("config_path", "")
            has_content = bool(self.profile.get("config_content"))

            if ep:
                text_info = f"🌐 <span style='color: #cbd5e1; font-weight: 600;'>{ep}</span>   <span style='color: #334155;'>|</span>   📡 <span style='color: #38bdf8;'>{addr or 'Авто'}</span>   <span style='color: #334155;'>|</span>   <span style='color: #94a3b8; font-family: monospace; background: rgba(255,255,255,0.05); padding: 2px 6px; border-radius: 4px;'>{iface}</span>"
            elif cfg_path:
                base_name = os.path.basename(cfg_path)
                text_info = f"📄 <span style='color: #cbd5e1; font-weight: 600;'>{base_name}</span>   <span style='color: #334155;'>|</span>   <span style='color: #94a3b8; font-family: monospace; background: rgba(255,255,255,0.05); padding: 2px 6px; border-radius: 4px;'>{iface}</span>"
            elif has_content:
                text_info = f"⚡ <span style='color: #cbd5e1; font-weight: 600;'>Конфиг сохранён в профиле</span>   <span style='color: #334155;'>|</span>   <span style='color: #94a3b8; font-family: monospace; background: rgba(255,255,255,0.05); padding: 2px 6px; border-radius: 4px;'>{iface}</span>"
            else:
                text_info = "<span style='color: #f87171; font-weight: 600;'>⚠ Конфигурация не настроена (откройте «⚙ Настройки»)</span>"

            details_label = QLabel(text_info)
            tooltip_parts = [f"Интерфейс: {iface}"]
            if ep:
                tooltip_parts.append(f"Шлюз (Endpoint): {ep}")
            if addr:
                tooltip_parts.append(f"Адрес (Address): {addr}")
            if self.profile.get("dns"):
                tooltip_parts.append(f"DNS: {self.profile.get('dns')}")
            if self.profile.get("obfuscation"):
                tooltip_parts.append("Обфускация: Активирована (AmneziaWG)")
            if cfg_path:
                tooltip_parts.append(f"Источник: {cfg_path}")
            details_label.setToolTip("\n".join(tooltip_parts))
        else:
            server = self.profile.get("server", "Не указан")
            port = self.profile.get("port", 443)
            cam = self.profile.get("camouflage", "")
            cam_info = f"   <span style='color: #334155;'>|</span>   🎭 <span style='color: #fbbf24; font-family: monospace;'>?{cam}</span>" if cam else ""
            user = self.profile.get("username", "")
            user_info = f"   <span style='color: #334155;'>|</span>   👤 <span style='color: #cbd5e1;'>{user}</span>" if user else ""
            details_label = QLabel(f"🌐 <span style='color: #cbd5e1; font-weight: 600;'>{server}:{port}</span>{cam_info}{user_info}")

        details_label.setTextFormat(Qt.RichText)
        details_label.setStyleSheet("font-size: 12px; color: #94a3b8;")
        details_row.addWidget(details_label)
        details_row.addStretch()

        # Кнопки управления (⚙ Настройки, 🗑 Удалить)
        self.btn_edit = QPushButton("⚙ Настройки")
        self.btn_edit.setObjectName("btn_card_edit")
        self.btn_edit.setCursor(Qt.PointingHandCursor)
        self.btn_edit.clicked.connect(lambda: self.edit_requested.emit(self.profile_id))
        details_row.addWidget(self.btn_edit)

        self.btn_delete = QPushButton("🗑 Удалить")
        self.btn_delete.setObjectName("btn_card_delete")
        self.btn_delete.setCursor(Qt.PointingHandCursor)
        self.btn_delete.clicked.connect(lambda: self.delete_requested.emit(self.profile_id))
        details_row.addWidget(self.btn_delete)

        card_layout.addLayout(details_row)

    def _on_toggle_clicked(self):
        if self.current_state == VPNState.CONNECTED:
            # Мгновенная визуальная реакция на клик отключения (0 мс)
            self.update_state(
                VPNState.DISCONNECTING,
                custom_status="⏳ Отключение...",
                custom_btn="Отключение..."
            )
            QApplication.processEvents()
            self.disconnect_requested.emit(self.profile_id)
        elif self.current_state in (VPNState.DISCONNECTED, VPNState.ERROR):
            # Мгновенная визуальная реакция на клик подключения (0 мс)
            self.update_state(
                VPNState.CONNECTING,
                custom_status="⏳ Подключение...",
                custom_btn="Подключение..."
            )
            QApplication.processEvents()
            self.connect_requested.emit(self.profile_id)

    def update_state(self, state: VPNState, custom_status: Optional[str] = None, custom_btn: Optional[str] = None):
        self.current_state = state

        # Устанавливаем динамическое состояние для стилизации рамки и градиента карточки в QSS
        state_key = "disconnected"
        if state == VPNState.CONNECTED:
            state_key = "connected"
        elif state in (VPNState.CONNECTING, VPNState.DISCONNECTING):
            state_key = "connecting"
        elif state == VPNState.ERROR:
            state_key = "error"

        self.setProperty("state", state_key)
        self.style().unpolish(self)
        self.style().polish(self)

        # Принудительно устанавливаем локальный стиль с градиентом и спекулярной гранью
        if state == VPNState.CONNECTED:
            self.setStyleSheet(CARD_STYLE_CONNECTED)
        elif state in (VPNState.CONNECTING, VPNState.DISCONNECTING):
            self.setStyleSheet(CARD_STYLE_CONNECTING)
        elif state == VPNState.ERROR:
            self.setStyleSheet(CARD_STYLE_ERROR)
        else:
            self.setStyleSheet(CARD_STYLE_DISCONNECTED)

        # Синхронизируем адаптивную контурную тень с новым состоянием
        self._apply_shadow(hover=self.underMouse())

        if state == VPNState.CONNECTED:
            self.lbl_status.setText(custom_status or "● Подключено")
            self.lbl_status.setStyleSheet("""
                color: #34d399;
                background-color: rgba(16, 185, 129, 0.12);
                border: 1px solid rgba(16, 185, 129, 0.35);
                border-radius: 12px;
                padding: 4px 12px;
                font-weight: 700;
                font-size: 11px;
            """)
            self.btn_toggle.setText(custom_btn or "Отключить")
            self.btn_toggle.setEnabled(True)
            self.btn_toggle.setObjectName("btn_disconnect")
            self.btn_toggle.setStyleSheet(DISCONNECT_BTN_STYLE)
            self.btn_toggle.style().unpolish(self.btn_toggle)
            self.btn_toggle.style().polish(self.btn_toggle)
            self.btn_delete.setEnabled(False)

        elif state == VPNState.CONNECTING:
            self.lbl_status.setText(custom_status or "⏳ Подключение...")
            self.lbl_status.setStyleSheet("""
                color: #fbbf24;
                background-color: rgba(217, 119, 6, 0.12);
                border: 1px solid rgba(217, 119, 6, 0.35);
                border-radius: 12px;
                padding: 4px 12px;
                font-weight: 700;
                font-size: 11px;
            """)
            self.btn_toggle.setText(custom_btn or "Подключение...")
            self.btn_toggle.setEnabled(False)
            self.btn_toggle.setObjectName("btn_connecting")
            self.btn_toggle.setStyleSheet(CONNECTING_BTN_STYLE)
            self.btn_toggle.style().unpolish(self.btn_toggle)
            self.btn_toggle.style().polish(self.btn_toggle)
            self.btn_delete.setEnabled(False)

        elif state == VPNState.DISCONNECTING:
            self.lbl_status.setText(custom_status or "⏳ Отключение...")
            self.lbl_status.setStyleSheet("""
                color: #fbbf24;
                background-color: rgba(217, 119, 6, 0.12);
                border: 1px solid rgba(217, 119, 6, 0.35);
                border-radius: 12px;
                padding: 4px 12px;
                font-weight: 700;
                font-size: 11px;
            """)
            self.btn_toggle.setText(custom_btn or "Отключение...")
            self.btn_toggle.setEnabled(False)
            self.btn_toggle.setObjectName("btn_connecting")
            self.btn_toggle.setStyleSheet(CONNECTING_BTN_STYLE)
            self.btn_toggle.style().unpolish(self.btn_toggle)
            self.btn_toggle.style().polish(self.btn_toggle)
            self.btn_delete.setEnabled(False)

        else:  # DISCONNECTED or ERROR
            error_mode = (state == VPNState.ERROR)
            status_text = custom_status or ("⚠ Ошибка" if error_mode else "○ Не активно")
            status_color = "#f87171" if error_mode else "#94a3b8"
            status_bg = "rgba(239, 68, 68, 0.12)" if error_mode else "rgba(255, 255, 255, 0.04)"
            status_border = "rgba(239, 68, 68, 0.35)" if error_mode else "rgba(255, 255, 255, 0.08)"

            self.lbl_status.setText(status_text)
            self.lbl_status.setStyleSheet(f"""
                color: {status_color};
                background-color: {status_bg};
                border: 1px solid {status_border};
                border-radius: 12px;
                padding: 4px 12px;
                font-weight: 600;
                font-size: 11px;
            """)

            action_text = custom_btn or "Подключить"
            self.btn_toggle.setText(action_text)
            self.btn_toggle.setEnabled(True)
            self.btn_toggle.setObjectName("btn_connect")
            self.btn_toggle.setStyleSheet(CONNECT_BTN_STYLE)
            self.btn_toggle.style().unpolish(self.btn_toggle)
            self.btn_toggle.style().polish(self.btn_toggle)
            self.btn_delete.setEnabled(True)
