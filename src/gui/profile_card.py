import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QWidget,
    QGraphicsDropShadowEffect, QSizePolicy, QMessageBox
)
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtCore import Qt, Signal, QUrl
from core.vpn_manager import VPNState
from gui.styles import get_amnezia_pixmap, get_openconnect_pixmap, get_subscription_pixmap
from utils.config_store import settings
from utils.subscription_manager import format_subscription_profile_name, SubscriptionManager


CONNECT_BTN_STYLE = """
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #10b981, stop:1 #059669);
    color: #ffffff;
    font-size: 13px;
    font-weight: 700;
    padding: 7px 14px;
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
    padding: 7px 14px;
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
    padding: 7px 12px;
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

CARD_STYLE_FROZEN = """
QFrame#vpn_profile_card {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #091929, stop:1 #06111d);
    border: 1px solid rgba(56, 189, 248, 0.40);
    border-top: 1px solid rgba(186, 230, 253, 0.75);
    border-radius: 12px;
}
QFrame#vpn_profile_card:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0e2338, stop:1 #081726);
    border: 1px solid rgba(56, 189, 248, 0.65);
    border-top: 1px solid rgba(186, 230, 253, 0.95);
    border-radius: 12px;
}
"""

FROZEN_BTN_STYLE = """
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(14, 165, 233, 0.18), stop:1 rgba(2, 132, 199, 0.18));
    color: #7dd3fc;
    font-size: 13px;
    font-weight: 700;
    padding: 7px 12px;
    border-radius: 8px;
    border: 1px solid rgba(56, 189, 248, 0.50);
    border-bottom: 2px solid rgba(2, 132, 199, 0.70);
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(14, 165, 233, 0.32), stop:1 rgba(2, 132, 199, 0.32));
    color: #e0f2fe;
    border: 1px solid rgba(125, 211, 252, 0.75);
    border-bottom: 2px solid #0284c7;
}
QPushButton:pressed {
    background-color: rgba(2, 132, 199, 0.40);
}
"""

BLOCKED_BTN_STYLE = """
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(220, 38, 38, 0.18), stop:1 rgba(185, 28, 28, 0.18));
    color: #fca5a5;
    font-size: 13px;
    font-weight: 700;
    padding: 7px 12px;
    border-radius: 8px;
    border: 1px solid rgba(239, 68, 68, 0.50);
    border-bottom: 2px solid rgba(185, 28, 28, 0.70);
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(220, 38, 38, 0.30), stop:1 rgba(185, 28, 28, 0.30));
    color: #ffffff;
    border: 1px solid rgba(248, 113, 113, 0.75);
    border-bottom: 2px solid #dc2626;
}
QPushButton:pressed {
    background-color: rgba(185, 28, 28, 0.40);
}
"""

EXPIRED_BTN_STYLE = """
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(217, 119, 6, 0.18), stop:1 rgba(180, 83, 9, 0.18));
    color: #fde047;
    font-size: 13px;
    font-weight: 700;
    padding: 7px 12px;
    border-radius: 8px;
    border: 1px solid rgba(245, 158, 11, 0.50);
    border-bottom: 2px solid rgba(180, 83, 9, 0.70);
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(217, 119, 6, 0.30), stop:1 rgba(180, 83, 9, 0.30));
    color: #ffffff;
    border: 1px solid rgba(251, 191, 36, 0.75);
    border-bottom: 2px solid #d97706;
}
QPushButton:pressed {
    background-color: rgba(180, 83, 9, 0.40);
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

    @property
    def state(self) -> VPNState:
        return self.current_state

    def enterEvent(self, event):
        super().enterEvent(event)
        self._apply_shadow(hover=True)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._apply_shadow(hover=False)

    def get_frozen_status(self) -> Tuple[bool, str]:
        """
        Проверяет, заморожен/заблокирован ли данный профиль по подписке.
        Возвращает кортеж: (is_frozen: bool, reason: str)
        где reason: 'blocked', 'expired', 'frozen' или ''.
        """
        raw_name = str(self.profile.get("name", "")).strip()
        raw_name_lower = raw_name.lower()
        is_sub = (
            bool(self.profile.get("is_subscription"))
            or self.profile.get("sub_id") is not None
            or raw_name_lower.endswith("-sub")
            or raw_name.endswith("-SUB")
            or " -sub" in raw_name_lower
            or " -SUB" in raw_name
        )
        if not is_sub:
            return (False, "")

        status = str(self.profile.get("subscription_status") or settings.get("subscription_status") or "").strip().lower()
        if status in ("blocked", "banned"):
            return (True, "blocked")
        if status in ("expired",):
            return (True, "expired")
        if status in ("frozen", "suspended"):
            return (True, "frozen")

        expires_at = self.profile.get("expires_at") or settings.get("subscription_expires_at", "")
        if expires_at:
            try:
                dt_clean = str(expires_at).replace("Z", "+00:00")
                dt = datetime.fromisoformat(dt_clean)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) > dt:
                    return (True, "expired")
            except Exception:
                pass

        return (False, "")

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
            is_frozen, _ = self.get_frozen_status()
            if is_frozen:
                # Эффект ледяной ауры заморозки (Icy Frost Glow)
                if hover:
                    self.shadow_effect.setColor(QColor(56, 189, 248, 90))
                    self.shadow_effect.setBlurRadius(24)
                    self.shadow_effect.setYOffset(4)
                else:
                    self.shadow_effect.setColor(QColor(56, 189, 248, 60))
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

        # Бейдж типа протокола с векторным значком
        proto_badge = QFrame()
        proto_badge.setObjectName("proto_badge")
        proto_badge.setFixedHeight(26)
        proto_badge_layout = QHBoxLayout(proto_badge)
        proto_badge_layout.setContentsMargins(6, 2, 8, 2)
        proto_badge_layout.setSpacing(5)

        lbl_proto_icon = QLabel()
        lbl_proto_icon.setFixedSize(14, 14)
        lbl_proto_icon.setScaledContents(True)

        lbl_proto_text = QLabel()

        if self.proto == "amnezia":
            proto_badge.setStyleSheet("""
                QFrame#proto_badge {
                    background-color: rgba(245, 158, 11, 0.12);
                    border: 1px solid rgba(245, 158, 11, 0.35);
                    border-radius: 6px;
                }
            """)
            lbl_proto_text.setText("AmneziaWG")
            lbl_proto_text.setStyleSheet("color: #fbbf24; font-size: 11px; font-weight: 800; background: transparent; border: none; padding: 0;")
            amz_pix = get_amnezia_pixmap(14, 14)
            if not amz_pix.isNull():
                lbl_proto_icon.setPixmap(amz_pix)
            else:
                lbl_proto_icon.setText("⚡")
        else:
            proto_badge.setStyleSheet("""
                QFrame#proto_badge {
                    background-color: rgba(34, 211, 238, 0.12);
                    border: 1px solid rgba(34, 211, 238, 0.35);
                    border-radius: 6px;
                }
            """)
            lbl_proto_text.setText("OpenConnect")
            lbl_proto_text.setStyleSheet("color: #22d3ee; font-size: 11px; font-weight: 800; background: transparent; border: none; padding: 0;")
            oc_pix = get_openconnect_pixmap(14, 14)
            if not oc_pix.isNull():
                lbl_proto_icon.setPixmap(oc_pix)
            else:
                lbl_proto_icon.setText("🛡")

        proto_badge_layout.addWidget(lbl_proto_icon)
        proto_badge_layout.addWidget(lbl_proto_text)
        top_row.addWidget(proto_badge)

        # Проверка, является ли профиль подписочным
        raw_name = str(self.profile.get("name", "")).strip()
        raw_name_lower = raw_name.lower()
        is_sub = (
            bool(self.profile.get("is_subscription"))
            or self.profile.get("sub_id") is not None
            or raw_name_lower.endswith("-sub")
            or raw_name.endswith("-SUB")
            or " -sub" in raw_name_lower
            or " -SUB" in raw_name
        )

        if is_sub:
            sub_badge = QFrame()
            sub_badge.setObjectName("sub_badge")
            sub_badge.setFixedHeight(26)
            sub_badge_layout = QHBoxLayout(sub_badge)
            sub_badge_layout.setContentsMargins(6, 2, 8, 2)
            sub_badge_layout.setSpacing(5)

            lbl_sub_icon = QLabel()
            lbl_sub_icon.setFixedSize(14, 14)
            lbl_sub_icon.setScaledContents(True)
            lbl_sub_icon.setStyleSheet("background: transparent; border: none; padding: 0;")

            lbl_sub_text = QLabel()

            expires_at = self.profile.get("expires_at") or settings.get("subscription_expires_at", "")
            exp_display = "Бессрочно"
            if expires_at:
                try:
                    dt = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
                    exp_display = dt.strftime("%d.%m.%Y")
                except Exception:
                    exp_display = str(expires_at)

            is_frozen, frozen_reason = self.get_frozen_status()
            if is_frozen:
                if frozen_reason == "blocked":
                    sub_badge.setStyleSheet("""
                        QFrame#sub_badge {
                            background-color: rgba(220, 38, 38, 0.20);
                            border: 1px solid rgba(239, 68, 68, 0.60);
                            border-radius: 6px;
                        }
                    """)
                    lbl_sub_icon.setText("⛔")
                    lbl_sub_text.setText("заблокировано")
                    lbl_sub_text.setStyleSheet("color: #fca5a5; font-size: 11px; font-weight: 800; background: transparent; border: none; padding: 0;")
                    sub_badge.setToolTip("⛔ Доступ заблокирован администратором")
                elif frozen_reason == "expired":
                    sub_badge.setStyleSheet("""
                        QFrame#sub_badge {
                            background-color: rgba(217, 119, 6, 0.20);
                            border: 1px solid rgba(245, 158, 11, 0.60);
                            border-radius: 6px;
                        }
                    """)
                    lbl_sub_icon.setText("⌛")
                    lbl_sub_text.setText("истекла")
                    lbl_sub_text.setStyleSheet("color: #fde047; font-size: 11px; font-weight: 800; background: transparent; border: none; padding: 0;")
                    sub_badge.setToolTip(f"⌛ Срок действия подписки истёк ({exp_display})")
                else:
                    sub_badge.setStyleSheet("""
                        QFrame#sub_badge {
                            background-color: rgba(14, 165, 233, 0.20);
                            border: 1px solid rgba(56, 189, 248, 0.60);
                            border-radius: 6px;
                        }
                    """)
                    lbl_sub_icon.setText("❄")
                    lbl_sub_text.setText("заморожено")
                    lbl_sub_text.setStyleSheet("color: #7dd3fc; font-size: 11px; font-weight: 800; background: transparent; border: none; padding: 0;")
                    sub_badge.setToolTip("❄ Подписка временно заморожена")
            else:
                sub_badge.setStyleSheet("""
                    QFrame#sub_badge {
                        background-color: rgba(168, 85, 247, 0.15);
                        border: 1px solid rgba(168, 85, 247, 0.45);
                        border-radius: 6px;
                    }
                """)
                sub_pix = get_subscription_pixmap(14, 14)
                if not sub_pix.isNull():
                    lbl_sub_icon.setPixmap(sub_pix)
                else:
                    lbl_sub_icon.setText("🔑")
                lbl_sub_text.setText("sub")
                lbl_sub_text.setStyleSheet("color: #c084fc; font-size: 11px; font-weight: 800; background: transparent; border: none; padding: 0;")
                sub_badge.setToolTip(f"Подключение получено по подписке (BobrDobr VPN)\nИстекает: {exp_display}")

            sub_badge_layout.addWidget(lbl_sub_icon)
            sub_badge_layout.addWidget(lbl_sub_text)
            top_row.addWidget(sub_badge)

        # Название профиля (для подписки гарантируем суффикс -sub)
        name_text = self.profile.get("name", "Без названия")
        if is_sub:
            name_text = format_subscription_profile_name(name_text)

        self.lbl_name = QLabel(name_text)
        self.lbl_name.setToolTip(name_text)
        self.lbl_name.setMinimumWidth(0)
        self.lbl_name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.lbl_name.setStyleSheet("font-size: 16px; font-weight: 800; color: #f8fafc; margin-left: 2px;")
        top_row.addWidget(self.lbl_name, stretch=1)

        # Правый контейнер верхнего ряда (Статус + Главная кнопка действия)
        top_right_box = QHBoxLayout()
        top_right_box.setSpacing(10)
        top_right_box.setContentsMargins(0, 0, 0, 0)
        top_right_box.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # Бейдж статуса
        self.lbl_status = QLabel("○ Отключено")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.lbl_status.setStyleSheet("font-size: 11px; font-weight: 700; color: #94a3b8; padding: 4px 10px;")
        top_right_box.addWidget(self.lbl_status)

        # Главная кнопка действия (Подключить / Отключить)
        self.btn_toggle = QPushButton("Подключить")
        self.btn_toggle.setObjectName("btn_connect")
        self.btn_toggle.setCursor(Qt.PointingHandCursor)
        self.btn_toggle.setFixedSize(148, 34)
        self.btn_toggle.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_toggle.clicked.connect(self._on_toggle_clicked)
        top_right_box.addWidget(self.btn_toggle)

        top_row.addLayout(top_right_box)
        card_layout.addLayout(top_row)

        # 2. Средний ряд: Детали соединения (Шлюз, Конфиг, Маскировка)
        details_row = QHBoxLayout()
        details_row.setSpacing(12)

        if self.proto == "amnezia":
            ep = self.profile.get("endpoint", "")
            addr = self.profile.get("address", "")
            iface = self.profile.get("interface", "bobr0")
            cfg_path = self.profile.get("config_path", "")
            has_content = bool(self.profile.get("config_content"))

            if ep:
                text_info = f"🌐 <span style='color: #cbd5e1; font-weight: 600;'>{ep}</span>   <span style='color: #334155;'>|</span>   📡 <span style='color: #fbbf24;'>{addr or 'Авто'}</span>   <span style='color: #334155;'>|</span>   <span style='color: #94a3b8; font-family: monospace; background: rgba(255,255,255,0.05); padding: 2px 6px; border-radius: 4px;'>{iface}</span>"
            elif cfg_path:
                base_name = os.path.basename(cfg_path)
                text_info = f"📄 <span style='color: #cbd5e1; font-weight: 600;'>{base_name}</span>   <span style='color: #334155;'>|</span>   <span style='color: #94a3b8; font-family: monospace; background: rgba(255,255,255,0.05); padding: 2px 6px; border-radius: 4px;'>{iface}</span>"
            elif has_content:
                text_info = f"🛡 <span style='color: #cbd5e1; font-weight: 600;'>Конфиг сохранён в профиле</span>   <span style='color: #334155;'>|</span>   <span style='color: #94a3b8; font-family: monospace; background: rgba(255,255,255,0.05); padding: 2px 6px; border-radius: 4px;'>{iface}</span>"
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
            cam_info = f"   <span style='color: #334155;'>|</span>   🎭 <span style='color: #22d3ee; font-family: monospace;'>?{cam}</span>" if cam else ""
            user = self.profile.get("username", "")
            user_info = f"   <span style='color: #334155;'>|</span>   👤 <span style='color: #cbd5e1;'>{user}</span>" if user else ""
            details_label = QLabel(f"🌐 <span style='color: #cbd5e1; font-weight: 600;'>{server}:{port}</span>{cam_info}{user_info}")

        details_label.setTextFormat(Qt.RichText)
        details_label.setMinimumWidth(0)
        details_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        details_label.setStyleSheet("font-size: 12px; color: #94a3b8;")
        details_row.addWidget(details_label, stretch=1)

        # Правый контейнер среднего ряда (⚙ Настройки, 🗑 Удалить)
        details_right_box = QHBoxLayout()
        details_right_box.setSpacing(8)
        details_right_box.setContentsMargins(0, 0, 0, 0)
        details_right_box.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.btn_edit = QPushButton("⚙ Настройки")
        self.btn_edit.setObjectName("btn_card_edit")
        self.btn_edit.setCursor(Qt.PointingHandCursor)
        self.btn_edit.setFixedSize(110, 28)
        self.btn_edit.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_edit.clicked.connect(lambda: self.edit_requested.emit(self.profile_id))
        details_right_box.addWidget(self.btn_edit)

        self.btn_delete = QPushButton("🗑 Удалить")
        self.btn_delete.setObjectName("btn_card_delete")
        self.btn_delete.setCursor(Qt.PointingHandCursor)
        self.btn_delete.setFixedSize(100, 28)
        self.btn_delete.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_delete.clicked.connect(lambda: self.delete_requested.emit(self.profile_id))
        details_right_box.addWidget(self.btn_delete)

        details_row.addLayout(details_right_box)
        card_layout.addLayout(details_row)

    def _on_toggle_clicked(self):
        if self.current_state in (VPNState.CONNECTING, VPNState.DISCONNECTING) or not self.btn_toggle.isEnabled():
            return

        if self.current_state == VPNState.CONNECTED:
            # Мгновенная визуальная реакция на клик отключения (0 мс)
            self.btn_toggle.setEnabled(False)
            self.update_state(
                VPNState.DISCONNECTING,
                custom_status="⏳ Отключение...",
                custom_btn="Отключение..."
            )
            QApplication.processEvents()
            self.disconnect_requested.emit(self.profile_id)
        elif self.current_state in (VPNState.DISCONNECTED, VPNState.ERROR):
            is_frozen, reason = self.get_frozen_status()
            if is_frozen:
                self._show_frozen_warning(reason)
                return

            # Мгновенная визуальная реакция на клик подключения (0 мс)
            self.btn_toggle.setEnabled(False)
            self.update_state(
                VPNState.CONNECTING,
                custom_status="⏳ Подключение...",
                custom_btn="Подключение..."
            )
            QApplication.processEvents()
            self.connect_requested.emit(self.profile_id)

    def _show_frozen_warning(self, reason: str):
        """Отображает диалог с предупреждением о заморозке подписки и предложением перейти в Личный Кабинет."""
        cabinet_url = SubscriptionManager.get_cabinet_url()
        username = settings.get("subscription_username") or self.profile.get("username") or "пользователя"

        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Warning)

        if reason == "blocked":
            msg_box.setWindowTitle("Доступ заблокирован")
            msg_box.setText(
                f"Пользователь подписки «{username}» заблокирован администратором.\n\n"
                "Подключение к этой плотине недоступно. Для восстановления доступа перейдите в личный кабинет или обратитесь к администратору BobrDobr VPN."
            )
        elif reason == "expired":
            msg_box.setWindowTitle("Срок подписки истёк")
            msg_box.setText(
                f"Срок действия подписки пользователя «{username}» истёк.\n\n"
                "Для восстановления доступа продлите подписку в личном кабинете BobrDobr VPN, затем обновите её."
            )
        else:
            msg_box.setWindowTitle("Подписка заморожена")
            msg_box.setText(
                f"Действие подписки пользователя «{username}» приостановлено.\n\n"
                "Для разморозки обратитесь к администратору или проверьте состояние в личном кабинете."
            )

        btn_open = None
        if cabinet_url:
            btn_open = msg_box.addButton("Перейти в личный кабинет ↗", QMessageBox.AcceptRole)
            btn_open.setCursor(Qt.PointingHandCursor)
            btn_open.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0284c7, stop:1 #0369a1);
                    color: #ffffff;
                    border: 1px solid rgba(255, 255, 255, 0.20);
                    border-radius: 6px;
                    padding: 6px 16px;
                    font-weight: 700;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0ea5e9, stop:1 #0284c7);
                }
            """)

        btn_close = msg_box.addButton("Закрыть", QMessageBox.RejectRole)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: #1a252a;
                color: #cbd5e1;
                border: 1px solid #334852;
                border-radius: 6px;
                padding: 6px 16px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #24343b;
            }
        """)
        msg_box.setDefaultButton(btn_open if btn_open else btn_close)
        msg_box.exec()

        if btn_open and msg_box.clickedButton() == btn_open:
            QDesktopServices.openUrl(QUrl(cabinet_url))

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

        is_frozen, frozen_reason = self.get_frozen_status()

        # Принудительно устанавливаем локальный стиль с градиентом и спекулярной гранью
        if state == VPNState.CONNECTED:
            self.setStyleSheet(CARD_STYLE_CONNECTED)
        elif state in (VPNState.CONNECTING, VPNState.DISCONNECTING):
            self.setStyleSheet(CARD_STYLE_CONNECTING)
        elif state == VPNState.ERROR:
            self.setStyleSheet(CARD_STYLE_ERROR)
        elif is_frozen:
            self.setStyleSheet(CARD_STYLE_FROZEN)
        else:
            self.setStyleSheet(CARD_STYLE_DISCONNECTED)

        # Синхронизируем адаптивную контурную тень с новым состоянием
        hover = self.underMouse() if hasattr(self, "underMouse") else False
        self._apply_shadow(hover=hover)

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

            if is_frozen and not error_mode:
                if frozen_reason == "blocked":
                    status_text = custom_status or "⛔ Заблокировано"
                    status_color = "#fca5a5"
                    status_bg = "rgba(220, 38, 38, 0.16)"
                    status_border = "rgba(239, 68, 68, 0.45)"
                    action_text = custom_btn or "⛔ Заблокировано"
                    btn_style = BLOCKED_BTN_STYLE
                elif frozen_reason == "expired":
                    status_text = custom_status or "⌛ Срок истёк"
                    status_color = "#fde047"
                    status_bg = "rgba(217, 119, 6, 0.16)"
                    status_border = "rgba(245, 158, 11, 0.45)"
                    action_text = custom_btn or "⌛ Истекла"
                    btn_style = EXPIRED_BTN_STYLE
                else:
                    status_text = custom_status or "❄ Заморожено"
                    status_color = "#7dd3fc"
                    status_bg = "rgba(14, 165, 233, 0.16)"
                    status_border = "rgba(56, 189, 248, 0.45)"
                    action_text = custom_btn or "❄ Заморожено"
                    btn_style = FROZEN_BTN_STYLE

                self.lbl_status.setText(status_text)
                self.lbl_status.setStyleSheet(f"""
                    color: {status_color};
                    background-color: {status_bg};
                    border: 1px solid {status_border};
                    border-radius: 12px;
                    padding: 4px 12px;
                    font-weight: 700;
                    font-size: 11px;
                """)
                self.btn_toggle.setText(action_text)
                self.btn_toggle.setEnabled(True)
                self.btn_toggle.setObjectName("btn_frozen")
                self.btn_toggle.setStyleSheet(btn_style)
                self.btn_toggle.style().unpolish(self.btn_toggle)
                self.btn_toggle.style().polish(self.btn_toggle)
                self.btn_delete.setEnabled(True)
                return

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
