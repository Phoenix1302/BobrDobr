"""
Subscription Management Dialog for BobrDobr VPN.
Provides detailed subscription status, expiration date & remaining days calculation,
credentials and server info, link copying with token masking,
scrollable list of linked profiles (with protocol icons, gateways, and routing modes),
interactive sync, and safe subscription deletion.
"""

import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple, List

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QScrollArea, QWidget, QMessageBox, QApplication,
    QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QIcon, QColor, QDesktopServices

from utils.config_store import settings
from utils.subscription_manager import (
    SubscriptionManager, SubscriptionError, format_subscription_profile_name
)
from gui.styles import (
    get_subscription_pixmap, get_amnezia_pixmap, get_openconnect_pixmap
)


def mask_subscription_url(url: str) -> str:
    """Masks secret token in subscription URL for safe display."""
    cleaned = (url or "").strip()
    if not cleaned:
        return "Ссылка не настроена"
    try:
        parts = cleaned.rstrip("/").rsplit("/", 1)
        if len(parts) == 2 and len(parts[1]) > 8:
            prefix, token = parts[0], parts[1]
            masked_token = "••••••••" + token[-4:]
            return f"{prefix}/{masked_token}"
    except Exception:
        pass
    return cleaned


def format_expiration_details(exp_val: Any) -> Tuple[str, str, bool]:
    """
    Parses expiration timestamp or ISO string.
    Returns (formatted_date_time, remaining_str, is_expired).
    """
    if not exp_val:
        return ("Бессрочно", "Бессрочно", False)

    dt: Optional[datetime] = None
    if isinstance(exp_val, (int, float)):
        try:
            dt = datetime.fromtimestamp(exp_val, tz=timezone.utc)
        except Exception:
            pass
    elif isinstance(exp_val, str):
        val = exp_val.strip()
        if val.isdigit():
            try:
                dt = datetime.fromtimestamp(int(val), tz=timezone.utc)
            except Exception:
                pass
        else:
            try:
                iso_str = val.replace("Z", "+00:00")
                dt = datetime.fromisoformat(iso_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except Exception:
                for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d.%m.%Y %H:%M:%S", "%d.%m.%Y"):
                    try:
                        parsed = datetime.strptime(val, fmt)
                        dt = parsed.replace(tzinfo=timezone.utc)
                        break
                    except Exception:
                        pass

    if not dt:
        return (str(exp_val), "", False)

    full_date_time = dt.strftime("%d.%m.%Y, %H:%M:%S")

    now_utc = datetime.now(timezone.utc)
    delta = dt - now_utc
    total_seconds = int(delta.total_seconds())

    if total_seconds > 0:
        days = delta.days
        hours = (total_seconds % 86400) // 3600
        if days > 0:
            remaining_str = f"Осталось: {days} дн."
        elif hours > 0:
            remaining_str = f"Осталось: {hours} ч."
        else:
            remaining_str = "Осталось: менее 1 ч."
        return (full_date_time, remaining_str, False)
    else:
        days_ago = abs(delta.days)
        remaining_str = f"Истекла ({days_ago} дн. назад)" if days_ago > 0 else "Истекла"
        return (full_date_time, remaining_str, True)


def format_last_sync(last_sync_val: Any) -> str:
    """Formats last sync timestamp into human-readable string."""
    if not last_sync_val:
        return "Не проводилась"
    try:
        val = str(last_sync_val).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(val)
        return dt.strftime("%d.%m.%Y, %H:%M:%S")
    except Exception:
        return str(last_sync_val)


class SubscriptionManageDialog(QDialog):
    """
    Диалог расширенного управления подпиской BobrDobr VPN.
    Выдержан в тёмной гидроинженерной эстетике BobrDobr.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Управление подпиской — BobrDobr VPN")
        self.resize(680, 700)
        self.setMinimumSize(660, 620)
        self.setStyleSheet("""
            QDialog {
                background-color: #0c1316;
                color: #e2e8f0;
            }
        """)

        self._full_url: str = ""
        self._init_ui()
        self._refresh_data()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(22, 20, 22, 20)
        main_layout.setSpacing(16)

        # 1. Шапка диалога
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        lbl_icon = QLabel()
        lbl_icon.setFixedSize(32, 32)
        lbl_icon.setScaledContents(True)
        sub_pix = get_subscription_pixmap(32, 32)
        if not sub_pix.isNull():
            lbl_icon.setPixmap(sub_pix)
        else:
            lbl_icon.setText("🔑")
            lbl_icon.setStyleSheet("font-size: 24px;")
        header_layout.addWidget(lbl_icon)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)

        dlg_title = QLabel("Управление подпиской")
        dlg_title.setStyleSheet("font-size: 18px; font-weight: 800; color: #f8fafc; letter-spacing: -0.3px;")
        title_vbox.addWidget(dlg_title)

        dlg_subtitle = QLabel("BobrDobr VPN Subscription & Hydro-engineering Center")
        dlg_subtitle.setStyleSheet("font-size: 11px; color: #94a3b8; font-weight: 500;")
        title_vbox.addWidget(dlg_subtitle)

        header_layout.addLayout(title_vbox)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # 2. Секция 1: "Информация о подписке" (Карточка с параметрами)
        self.card_info = QFrame()
        self.card_info.setObjectName("sub_info_card")
        self.card_info.setStyleSheet("""
            QFrame#sub_info_card {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #18232a, stop:1 #0f161a);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-top: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 12px;
            }
        """)
        info_layout = QVBoxLayout(self.card_info)
        info_layout.setContentsMargins(16, 14, 16, 14)
        info_layout.setSpacing(10)

        # Верхняя строка карточки: Заголовок + Бейдж статуса
        status_row = QHBoxLayout()
        lbl_sec1_title = QLabel("Параметры подписки")
        lbl_sec1_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #c084fc;")
        status_row.addWidget(lbl_sec1_title)
        status_row.addStretch()

        self.lbl_status_badge = QLabel("● Активна")
        self.lbl_status_badge.setStyleSheet("""
            color: #34d399;
            background-color: rgba(16, 185, 129, 0.14);
            border: 1px solid rgba(16, 185, 129, 0.35);
            border-radius: 10px;
            padding: 3px 10px;
            font-weight: 700;
            font-size: 11px;
        """)
        status_row.addWidget(self.lbl_status_badge)
        info_layout.addLayout(status_row)

        # Разделитель
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.HLine)
        sep1.setStyleSheet("background-color: rgba(255, 255, 255, 0.06); max-height: 1px;")
        info_layout.addWidget(sep1)

        # Срок действия доступа
        self.lbl_expires = QLabel()
        self.lbl_expires.setTextFormat(Qt.RichText)
        self.lbl_expires.setStyleSheet("font-size: 12px; color: #cbd5e1;")
        info_layout.addWidget(self.lbl_expires)

        # Пользователь и Сервер
        self.lbl_user_server = QLabel()
        self.lbl_user_server.setTextFormat(Qt.RichText)
        self.lbl_user_server.setStyleSheet("font-size: 12px; color: #cbd5e1;")
        info_layout.addWidget(self.lbl_user_server)

        # Ссылка подписки (с маскированием и кнопкой копирования)
        url_header_lbl = QLabel("Ссылка подписки:")
        url_header_lbl.setStyleSheet("font-size: 12px; color: #94a3b8; font-weight: 600;")
        info_layout.addWidget(url_header_lbl)

        url_row = QHBoxLayout()
        url_row.setSpacing(8)

        self.input_url = QLineEdit()
        self.input_url.setReadOnly(False)
        self.input_url.setClearButtonEnabled(True)
        self.input_url.setPlaceholderText("Вставьте ссылку на подписку (https://...)")
        self.input_url.setFixedHeight(36)
        self.input_url.setStyleSheet("""
            QLineEdit {
                background-color: #0f161a;
                color: #e2e8f0;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 6px;
                padding: 0 10px;
                font-family: monospace;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #c084fc;
                color: #ffffff;
            }
        """)
        self.input_url.textChanged.connect(self._on_url_text_changed)
        url_row.addWidget(self.input_url, stretch=1)

        self.btn_paste_url = QPushButton("📥 Вставить")
        self.btn_paste_url.setCursor(Qt.PointingHandCursor)
        self.btn_paste_url.setFixedHeight(36)
        self.btn_paste_url.setFixedWidth(100)
        self.btn_paste_url.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 0 10px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #ffffff;
                border-color: #475569;
            }
        """)
        self.btn_paste_url.setToolTip("Вставить ссылку на подписку из буфера обмена")
        self.btn_paste_url.clicked.connect(self._on_paste_url_clicked)
        url_row.addWidget(self.btn_paste_url)

        self.btn_copy_url = QPushButton("📋 Скопировать")
        self.btn_copy_url.setCursor(Qt.PointingHandCursor)
        self.btn_copy_url.setFixedHeight(36)
        self.btn_copy_url.setFixedWidth(120)
        self.btn_copy_url.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 0 10px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #ffffff;
                border-color: #475569;
            }
        """)
        self.btn_copy_url.setToolTip("Скопировать полную ссылку подписки в буфер обмена")
        self.btn_copy_url.clicked.connect(self._on_copy_url_clicked)
        url_row.addWidget(self.btn_copy_url)
        info_layout.addLayout(url_row)

        # Время последней синхронизации
        self.lbl_last_sync = QLabel()
        self.lbl_last_sync.setTextFormat(Qt.RichText)
        self.lbl_last_sync.setStyleSheet("font-size: 11px; color: #64748b;")
        info_layout.addWidget(self.lbl_last_sync)

        main_layout.addWidget(self.card_info)

        # 3. Секция 2: "Связанные подключения ({N})"
        conn_header_row = QHBoxLayout()
        self.lbl_conn_title = QLabel("Связанные подключения (0)")
        self.lbl_conn_title.setStyleSheet("font-size: 14px; font-weight: 800; color: #f8fafc;")
        conn_header_row.addWidget(self.lbl_conn_title)
        conn_header_row.addStretch()
        main_layout.addLayout(conn_header_row)

        # Прокручиваемый список карточек подключений
        self.scroll_conn = QScrollArea()
        self.scroll_conn.setWidgetResizable(True)
        self.scroll_conn.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_conn.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_conn.setStyleSheet("""
            QScrollArea {
                background: #090e11;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
            }
        """)

        self.conn_container = QWidget()
        self.conn_container.setStyleSheet("background: transparent;")
        self.conn_layout = QVBoxLayout(self.conn_container)
        self.conn_layout.setContentsMargins(10, 10, 10, 10)
        self.conn_layout.setSpacing(8)
        self.scroll_conn.setWidget(self.conn_container)
        main_layout.addWidget(self.scroll_conn, stretch=1)

        # 4. Нижняя панель действий
        buttons_row = QHBoxLayout()
        buttons_row.setContentsMargins(0, 8, 0, 0)
        buttons_row.setSpacing(10)

        # Левая часть: Кнопка удаления подписки (Danger)
        self.btn_delete_sub = QPushButton("🗑 Удалить подписку")
        self.btn_delete_sub.setCursor(Qt.PointingHandCursor)
        self.btn_delete_sub.setFixedHeight(38)
        self.btn_delete_sub.setMinimumWidth(150)
        self.btn_delete_sub.setStyleSheet("""
            QPushButton {
                background-color: rgba(239, 68, 68, 0.12);
                color: #fca5a5;
                border: 1px solid rgba(239, 68, 68, 0.35);
                border-radius: 8px;
                padding: 6px 14px;
                font-weight: 700;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: rgba(239, 68, 68, 0.25);
                border-color: #ef4444;
                color: #ffffff;
            }
        """)
        self.btn_delete_sub.setToolTip("Удалить профили подписки и отвязать сервер. Ручные профили останутся.")
        self.btn_delete_sub.clicked.connect(self._on_delete_sub_clicked)
        buttons_row.addWidget(self.btn_delete_sub)

        buttons_row.addStretch(1)

        # Правая группа кнопок: [Личный кабинет ↗] [🔄 Обновить подписку] [Закрыть]
        right_btn_layout = QHBoxLayout()
        right_btn_layout.setSpacing(10)
        right_btn_layout.setContentsMargins(0, 0, 0, 0)

        # Кнопка перехода в Личный Кабинет
        self.btn_cabinet = QPushButton("Личный кабинет ↗")
        self.btn_cabinet.setObjectName("btn_cabinet")
        self.btn_cabinet.setCursor(Qt.PointingHandCursor)
        self.btn_cabinet.setFixedHeight(38)
        self.btn_cabinet.setMinimumWidth(140)
        self.btn_cabinet.setStyleSheet("""
            QPushButton#btn_cabinet {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0284c7, stop:1 #0369a1);
                color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-bottom: 2px solid #075985;
                border-radius: 8px;
                padding: 6px 14px;
                font-weight: 700;
                font-size: 12px;
            }
            QPushButton#btn_cabinet:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0ea5e9, stop:1 #0284c7);
                border-color: rgba(255, 255, 255, 0.28);
            }
            QPushButton#btn_cabinet:disabled {
                background-color: rgba(255, 255, 255, 0.05);
                color: #64748b;
                border: 1px solid rgba(255, 255, 255, 0.06);
            }
        """)
        self.btn_cabinet.clicked.connect(self._on_open_cabinet_clicked)
        right_btn_layout.addWidget(self.btn_cabinet)

        # Кнопка ручной синхронизации (Primary/Purple)
        self.btn_sync = QPushButton("🔄 Обновить подписку")
        self.btn_sync.setCursor(Qt.PointingHandCursor)
        self.btn_sync.setFixedHeight(38)
        self.btn_sync.setMinimumWidth(160)
        self.btn_sync.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #9333ea, stop:1 #7e22ce);
                color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-bottom: 2px solid #6b21a8;
                border-radius: 8px;
                padding: 6px 16px;
                font-weight: 700;
                font-size: 12px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #a855f7, stop:1 #9333ea);
                border-color: rgba(255, 255, 255, 0.28);
            }
            QPushButton:disabled {
                background-color: rgba(255, 255, 255, 0.06);
                color: #64748b;
                border: 1px solid rgba(255, 255, 255, 0.08);
            }
        """)
        self.btn_sync.clicked.connect(self._on_sync_clicked)
        right_btn_layout.addWidget(self.btn_sync)

        # Кнопка закрытия (Secondary)
        self.btn_close = QPushButton("Закрыть")
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.setFixedHeight(38)
        self.btn_close.setMinimumWidth(95)
        self.btn_close.setStyleSheet("""
            QPushButton {
                background-color: #1a252a;
                color: #cbd5e1;
                border: 1px solid #334852;
                border-radius: 8px;
                padding: 6px 16px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #24343b;
                color: #ffffff;
                border-color: #475569;
            }
        """)
        self.btn_close.clicked.connect(self.reject)
        right_btn_layout.addWidget(self.btn_close)

        buttons_row.addLayout(right_btn_layout)
        main_layout.addLayout(buttons_row)

    def _refresh_data(self):
        """Перечитывает данные подписки и профилей из ConfigStore и перерисовывает интерфейс."""
        info = SubscriptionManager.get_info()
        self._full_url = info.get("url", "")
        self._cabinet_url = info.get("cabinet_url") or SubscriptionManager.get_cabinet_url(self._full_url)
        if hasattr(self, "input_url"):
            if self._full_url:
                self.input_url.setText(mask_subscription_url(self._full_url))
                self.input_url.setToolTip(self._full_url)
            else:
                self.input_url.setText("")
                self.input_url.setPlaceholderText("Вставьте ссылку на подписку (https://...)")
                self.input_url.setToolTip("Ссылка не настроена. Вставьте ссылку для синхронизации.")

        if hasattr(self, "btn_cabinet"):
            if self._cabinet_url:
                self.btn_cabinet.setEnabled(True)
                self.btn_cabinet.setToolTip(f"Перейти в личный кабинет:\n{self._cabinet_url}")
            else:
                self.btn_cabinet.setEnabled(False)
                self.btn_cabinet.setToolTip("Личный кабинет недоступен (URL не определен)")

        # 1. Дата окончания и расчёт оставшихся дней
        expires_at = info.get("expires_at", "")
        full_dt, remaining_str, is_expired = format_expiration_details(expires_at)

        if expires_at:
            if is_expired:
                exp_html = (
                    f"📅 Срок окончания: <span style='color: #f87171; font-weight: 700;'>{full_dt}</span> "
                    f"<span style='color: #f87171; background: rgba(239,68,68,0.14); padding: 2px 7px; "
                    f"border: 1px solid rgba(239,68,68,0.35); border-radius: 4px; font-weight: 700;'>{remaining_str}</span>"
                )
            else:
                exp_html = (
                    f"📅 Срок окончания: <span style='color: #f8fafc; font-weight: 700;'>{full_dt}</span> "
                    f"<span style='color: #34d399; background: rgba(16,185,129,0.14); padding: 2px 7px; "
                    f"border: 1px solid rgba(16,185,129,0.35); border-radius: 4px; font-weight: 700;'>{remaining_str}</span>"
                )
        else:
            exp_html = "📅 Срок окончания: <span style='color: #34d399; font-weight: 700;'>Бессрочно</span>"
        self.lbl_expires.setText(exp_html)

        # 2. Пользователь и Сервер
        username = info.get("username", "") or "Не указан"
        server_host = info.get("server_host", "") or "Не указан"
        self.lbl_user_server.setText(
            f"👤 Пользователь: <span style='color: #f8fafc; font-weight: 700;'>{username}</span>    "
            f"<span style='color: #334155;'>|</span>    "
            f"🌐 Сервер: <span style='color: #38bdf8; font-weight: 700;'>{server_host}</span>"
        )

        # 3. Время последней синхронизации
        last_sync = format_last_sync(info.get("last_sync", ""))
        self.lbl_last_sync.setText(f"🕒 Последняя синхронизация: <span style='color: #cbd5e1;'>{last_sync}</span>")

        # 4. Статус подписки с бейджем
        status = str(info.get("status", "")).strip().lower()
        if not self._full_url and not info.get("profiles"):
            self.lbl_status_badge.setText("○ Не активна")
            self.lbl_status_badge.setStyleSheet("""
                color: #94a3b8;
                background-color: rgba(148, 163, 184, 0.14);
                border: 1px solid rgba(148, 163, 184, 0.35);
                border-radius: 10px;
                padding: 3px 10px;
                font-weight: 700;
                font-size: 11px;
            """)
        elif status == "blocked":
            self.lbl_status_badge.setText("⛔ Заблокирована")
            self.lbl_status_badge.setStyleSheet("""
                color: #f87171;
                background-color: rgba(239, 68, 68, 0.14);
                border: 1px solid rgba(239, 68, 68, 0.35);
                border-radius: 10px;
                padding: 3px 10px;
                font-weight: 700;
                font-size: 11px;
            """)
        elif is_expired or status == "expired":
            self.lbl_status_badge.setText("⚠ Истекла")
            self.lbl_status_badge.setStyleSheet("""
                color: #f87171;
                background-color: rgba(239, 68, 68, 0.14);
                border: 1px solid rgba(239, 68, 68, 0.35);
                border-radius: 10px;
                padding: 3px 10px;
                font-weight: 700;
                font-size: 11px;
            """)
        else:
            self.lbl_status_badge.setText("● Активна")
            self.lbl_status_badge.setStyleSheet("""
                color: #34d399;
                background-color: rgba(16, 185, 129, 0.14);
                border: 1px solid rgba(16, 185, 129, 0.35);
                border-radius: 10px;
                padding: 3px 10px;
                font-weight: 700;
                font-size: 11px;
            """)

        # 5. Отрисовка списка связанных подключений
        profiles = info.get("profiles", [])
        self.lbl_conn_title.setText(f"Связанные подключения ({len(profiles)})")

        # Очищаем текущие виджеты списка
        while self.conn_layout.count():
            item = self.conn_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not profiles:
            lbl_empty = QLabel("Нет связанных подключений. Нажмите «Обновить подписку» для синхронизации.")
            lbl_empty.setAlignment(Qt.AlignCenter)
            lbl_empty.setStyleSheet("color: #64748b; font-size: 12px; padding: 24px 10px;")
            self.conn_layout.addWidget(lbl_empty)
        else:
            for p in profiles:
                row_card = self._create_profile_item_card(p)
                self.conn_layout.addWidget(row_card)

        self.conn_layout.addStretch()

    def _create_profile_item_card(self, profile: Dict[str, Any]) -> QFrame:
        """Создает плашку для отображения одного подключения из подписки."""
        card = QFrame()
        card.setObjectName("sub_profile_item_card")
        card.setMinimumHeight(48)
        card.setStyleSheet("""
            QFrame#sub_profile_item_card {
                background-color: #121a1f;
                border: 1px solid rgba(255, 255, 255, 0.07);
                border-radius: 8px;
            }
            QFrame#sub_profile_item_card:hover {
                background-color: #162027;
                border-color: rgba(255, 255, 255, 0.16);
            }
        """)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        proto = str(profile.get("proto", "amnezia")).strip().lower()

        # Значок протокола
        lbl_icon = QLabel()
        lbl_icon.setFixedSize(16, 16)
        lbl_icon.setScaledContents(True)

        if proto == "amnezia":
            pix = get_amnezia_pixmap(16, 16)
            if not pix.isNull():
                lbl_icon.setPixmap(pix)
            else:
                lbl_icon.setText("⚡")
            proto_badge_txt = "AmneziaWG"
            proto_badge_style = "color: #fbbf24; background-color: rgba(245, 158, 11, 0.12); border: 1px solid rgba(245, 158, 11, 0.35);"
            gateway = profile.get("endpoint") or profile.get("address") or "bobr0"
        else:
            pix = get_openconnect_pixmap(16, 16)
            if not pix.isNull():
                lbl_icon.setPixmap(pix)
            else:
                lbl_icon.setText("🛡")
            proto_badge_txt = "OpenConnect"
            proto_badge_style = "color: #22d3ee; background-color: rgba(34, 211, 238, 0.12); border: 1px solid rgba(34, 211, 238, 0.35);"
            server = profile.get("server", "Не указан")
            port = profile.get("port", 443)
            gateway = f"{server}:{port}"

        layout.addWidget(lbl_icon)

        # Бейдж протокола
        lbl_proto = QLabel(proto_badge_txt)
        lbl_proto.setStyleSheet(f"{proto_badge_style} font-size: 11px; font-weight: 700; border-radius: 6px; padding: 2px 7px;")
        layout.addWidget(lbl_proto)

        # Название подключения (гарантируем суффикс -sub)
        p_name = format_subscription_profile_name(profile.get("name", "VPN"))
        lbl_name = QLabel(p_name)
        lbl_name.setToolTip(p_name)
        lbl_name.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        lbl_name.setStyleSheet("font-size: 13px; font-weight: 700; color: #f8fafc;")
        layout.addWidget(lbl_name)

        # Бейдж режима маршрутизации (split / full)
        mode = str(profile.get("mode", "split")).strip().lower()
        mode_text = "split" if mode == "split" else "full"
        lbl_mode = QLabel(mode_text)
        lbl_mode.setStyleSheet("""
            color: #94a3b8;
            background-color: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.10);
            border-radius: 5px;
            padding: 2px 6px;
            font-size: 10px;
            font-weight: 700;
            font-family: monospace;
        """)
        lbl_mode.setToolTip(f"Режим маршрутизации: {'Раздельный туннель (split)' if mode == 'split' else 'Полный туннель (full)'}")
        layout.addWidget(lbl_mode)

        layout.addStretch()

        # Шлюз (Endpoint / Server)
        lbl_gw = QLabel(f"🌐 {gateway}")
        lbl_gw.setToolTip(f"Шлюз подключения: {gateway}")
        lbl_gw.setStyleSheet("font-size: 12px; color: #94a3b8; font-weight: 500;")
        layout.addWidget(lbl_gw)

        return card

    def _on_open_cabinet_clicked(self):
        """Открывает веб-страницу Личного Кабинета в браузере."""
        cabinet_url = getattr(self, "_cabinet_url", "") or SubscriptionManager.get_cabinet_url(self._full_url)
        if cabinet_url:
            QDesktopServices.openUrl(QUrl(cabinet_url))
        else:
            QMessageBox.information(self, "Личный кабинет", "Ссылка на личный кабинет не определена.")

    def _on_url_text_changed(self, text: str):
        cleaned = text.strip()
        if cleaned and "••••" not in cleaned:
            self._full_url = cleaned
            settings.set("subscription_url", cleaned)
            new_cabinet = SubscriptionManager.get_cabinet_url(cleaned)
            if new_cabinet:
                self._cabinet_url = new_cabinet
                if hasattr(self, "btn_cabinet"):
                    self.btn_cabinet.setEnabled(True)
                    self.btn_cabinet.setToolTip(f"Перейти в личный кабинет:\n{self._cabinet_url}")

    def _on_paste_url_clicked(self):
        clipboard = QApplication.clipboard()
        text = (clipboard.text() if clipboard else "").strip()
        if not text:
            return
        self._full_url = text
        settings.set("subscription_url", text)
        if hasattr(self, "input_url"):
            self.input_url.setText(text)
            self.input_url.setToolTip(text)
        self._refresh_data()

    def _on_copy_url_clicked(self):
        """Копирует полную ссылку подписки в системный буфер обмена."""
        url_to_copy = self._full_url or (self.input_url.text().strip() if hasattr(self, "input_url") else "")
        if not url_to_copy or ("••••" in url_to_copy and not self._full_url):
            return
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self._full_url if self._full_url else url_to_copy)
        if hasattr(self, "btn_copy_url"):
            self.btn_copy_url.setText("✔ Скопировано!")
            self.btn_copy_url.setStyleSheet("""
                QPushButton {
                    background-color: #047857;
                    color: #ffffff;
                    border: 1px solid #10b981;
                    border-radius: 6px;
                    padding: 0 10px;
                    font-size: 12px;
                    font-weight: 700;
                }
            """)
            QTimer.singleShot(2000, self._restore_copy_btn)

    def _restore_copy_btn(self):
        try:
            if hasattr(self, "btn_copy_url"):
                self.btn_copy_url.setText("📋 Скопировать")
                self.btn_copy_url.setStyleSheet("""
                    QPushButton {
                        background-color: #1e293b;
                        color: #e2e8f0;
                        border: 1px solid #334155;
                        border-radius: 6px;
                        padding: 0 10px;
                        font-size: 12px;
                        font-weight: 600;
                    }
                    QPushButton:hover {
                        background-color: #334155;
                        color: #ffffff;
                        border-color: #475569;
                    }
                """)
        except RuntimeError:
            pass

    def _on_sync_clicked(self):
        """Вызывает синхронизацию подписки и обновляет диалог и главное окно."""
        input_text = self.input_url.text().strip() if hasattr(self, "input_url") else ""
        if input_text and "••••" not in input_text:
            url = input_text
            self._full_url = input_text
            settings.set("subscription_url", input_text)
        else:
            url = self._full_url or (settings.get("subscription_url") or "").strip()

        if not url:
            QMessageBox.warning(self, "Ошибка", "Ссылка на подписку не найдена. Вставьте ссылку на подписку в поле выше.")
            return

        self.btn_sync.setEnabled(False)
        self.btn_sync.setText("⏳ Обновление...")
        QApplication.processEvents()

        try:
            ok, msg, updated = SubscriptionManager.sync(url)
        except Exception as e:
            ok, msg, updated = False, str(e), []

        self.btn_sync.setEnabled(True)
        self.btn_sync.setText("🔄 Обновить подписку")

        self._refresh_data()

        # Обновляем список профилей в родительском главном окне
        parent_w = self.parent()
        if parent_w and hasattr(parent_w, "_render_profiles"):
            parent_w._render_profiles()
        if parent_w and hasattr(parent_w, "_update_subscription_ui"):
            parent_w._update_subscription_ui()

        if ok:
            QMessageBox.information(self, "Подписка обновлена", msg)
        else:
            QMessageBox.warning(self, "Ошибка обновления подписки", msg)

    def _on_delete_sub_clicked(self):
        """Запрашивает подтверждение и удаляет подписку и все связанные подключения."""
        profiles = [p for p in settings.get_profiles() if p.get("is_subscription") or p.get("sub_id") is not None]
        count = len(profiles)

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Удаление подписки")
        msg_box.setText(
            f"Вы действительно хотите удалить подписку и все связанные подключения ({count} шт.)?\n\n"
            "Ручные подключения останутся без изменений."
        )
        msg_box.setIcon(QMessageBox.Warning)

        btn_confirm = msg_box.addButton("Удалить подписку", QMessageBox.DestructiveRole)
        btn_confirm.setObjectName("btn_danger")
        btn_confirm.setCursor(Qt.PointingHandCursor)
        btn_confirm.setStyleSheet("""
            QPushButton {
                background-color: #dc2626;
                color: #ffffff;
                border: 1px solid #b91c1c;
                border-radius: 6px;
                padding: 6px 16px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #ef4444;
            }
        """)

        btn_cancel = msg_box.addButton("Отмена", QMessageBox.RejectRole)
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #1a252a;
                color: #cbd5e1;
                border: 1px solid #334852;
                border-radius: 6px;
                padding: 6px 16px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #24343b;
            }
        """)
        msg_box.setDefaultButton(btn_cancel)
        msg_box.exec()

        if msg_box.clickedButton() == btn_confirm:
            SubscriptionManager.clear()

            parent_w = self.parent()
            if parent_w and hasattr(parent_w, "_render_profiles"):
                parent_w._render_profiles()
            if parent_w and hasattr(parent_w, "_update_subscription_ui"):
                parent_w._update_subscription_ui()

            self.accept()
