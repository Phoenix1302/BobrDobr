"""
Instance Conflict and Ghost Process Dialog for BobrDobr VPN.
Provides user-friendly interaction when another instance is already running
or an orphaned background process is blocking startup.
"""

from typing import Dict, Any, Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QApplication
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon


class InstanceConflictDialog(QDialog):
    """
    Dialog displayed when a duplicate or hung instance of BobrDobr VPN is detected on startup.
    Allows user to switch to existing instance, or terminate it cleanly and launch this one.
    """

    def __init__(
        self,
        proc_info: Optional[Dict[str, Any]] = None,
        is_ghost: bool = False,
        app_icon: Optional[QIcon] = None,
        parent=None
    ):
        super().__init__(parent)
        self.proc_info = proc_info or {}
        self.is_ghost = is_ghost

        pid = self.proc_info.get("pid", "—")
        mode = self.proc_info.get("mode", "Другой экземпляр")

        if self.is_ghost:
            self.setWindowTitle("БобрДобр VPN — Обнаружен фоновый процесс")
        else:
            self.setWindowTitle("БобрДобр VPN — Экземпляр уже запущен")

        if app_icon and not app_icon.isNull():
            self.setWindowIcon(app_icon)

        self.setMinimumWidth(540)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 20, 24, 20)

        # 1. Header
        if self.is_ghost:
            title_text = "⚠️  Обнаружен зависший или фоновый процесс"
            title_color = "#f59e0b"  # amber
            subtitle_text = "Предыдущий сеанс не завершился до конца либо процесс остался в памяти."
        else:
            title_text = "🔄  Экземпляр программы уже запущен"
            title_color = "#38bdf8"  # sky blue
            subtitle_text = "Активное окно найдено и выведено на передний план вашего экрана."

        lbl_title = QLabel(title_text)
        lbl_title.setStyleSheet(f"font-size: 16px; font-weight: 800; color: {title_color};")
        lbl_title.setWordWrap(True)
        layout.addWidget(lbl_title)

        lbl_sub = QLabel(subtitle_text)
        lbl_sub.setWordWrap(True)
        lbl_sub.setStyleSheet("color: #cbd5e1; font-size: 13px; line-height: 1.4;")
        layout.addWidget(lbl_sub)

        # 2. Process details frame
        box = QFrame()
        box.setStyleSheet("background-color: #182226; border: 1px solid #283941; border-radius: 8px; padding: 12px;")
        box_layout = QVBoxLayout(box)
        box_layout.setSpacing(8)

        lbl_mode = QLabel(f"<b>Версия:</b> <span style='color: #f8fafc;'>{mode}</span>")
        lbl_mode.setStyleSheet("color: #94a3b8; font-size: 12px;")
        box_layout.addWidget(lbl_mode)

        lbl_pid = QLabel(f"<b>PID процесса:</b> <span style='color: #38bdf8;'>{pid}</span>")
        lbl_pid.setStyleSheet("color: #94a3b8; font-size: 12px;")
        box_layout.addWidget(lbl_pid)

        if self.is_ghost:
            lbl_status = QLabel("<b>Состояние:</b> <span style='color: #f87171;'>Окно не отвечает / процесс в фоне</span>")
        else:
            lbl_status = QLabel("<b>Состояние:</b> <span style='color: #34d399;'>Активен (окно развёрнуто)</span>")
        lbl_status.setStyleSheet("color: #94a3b8; font-size: 12px;")
        box_layout.addWidget(lbl_status)

        layout.addWidget(box)

        # 3. Explanatory message
        if self.is_ghost:
            desc_text = (
                "Фоновый процесс блокирует виртуальный адаптер Wintun и конфигурационные файлы.\n\n"
                "Вы можете принудительно завершить зависший процесс (при необходимости будет запрошено "
                "подтверждение Администратора Windows через UAC) и продолжить запуск."
            )
        else:
            desc_text = (
                "Одновременная работа нескольких экземпляров заблокирована во избежание "
                "конфликтов сетевых маршрутов и виртуальных интерфейсов Wintun.\n\n"
                "Вы хотите переключиться на работающий экземпляр или завершить его "
                "и запустить эту версию?"
            )

        lbl_desc = QLabel(desc_text)
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet("color: #94a3b8; font-size: 12px; line-height: 1.4;")
        layout.addWidget(lbl_desc)

        # 4. Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        if self.is_ghost:
            btn_cancel = QPushButton("Отмена")
            btn_cancel.setCursor(Qt.PointingHandCursor)
            btn_cancel.setStyleSheet("""
                QPushButton {
                    background-color: #1e293b;
                    color: #cbd5e1;
                    border: 1px solid #334155;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-size: 13px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background-color: #334155;
                    color: #ffffff;
                }
            """)
            btn_cancel.clicked.connect(self.reject)
            btn_layout.addWidget(btn_cancel)

            btn_kill = QPushButton("⚡ Завершить процесс и запустить")
            btn_kill.setCursor(Qt.PointingHandCursor)
            btn_kill.setDefault(True)
            btn_kill.setStyleSheet("""
                QPushButton {
                    background-color: #d97706;
                    color: #ffffff;
                    border: none;
                    border-radius: 6px;
                    padding: 8px 18px;
                    font-size: 13px;
                    font-weight: 700;
                }
                QPushButton:hover {
                    background-color: #b45309;
                }
            """)
            btn_kill.clicked.connect(self.accept)
            btn_layout.addWidget(btn_kill)
        else:
            btn_keep = QPushButton("Оставить активное окно")
            btn_keep.setCursor(Qt.PointingHandCursor)
            btn_keep.setDefault(True)
            btn_keep.setStyleSheet("""
                QPushButton {
                    background-color: #1e293b;
                    color: #f8fafc;
                    border: 1px solid #3b82f6;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-size: 13px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background-color: #2563eb;
                    color: #ffffff;
                }
            """)
            btn_keep.clicked.connect(self.reject)
            btn_layout.addWidget(btn_keep)

            btn_kill = QPushButton("⚡ Завершить другой экземпляр и запустить здесь")
            btn_kill.setCursor(Qt.PointingHandCursor)
            btn_kill.setStyleSheet("""
                QPushButton {
                    background-color: #dc2626;
                    color: #ffffff;
                    border: none;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-size: 13px;
                    font-weight: 700;
                }
                QPushButton:hover {
                    background-color: #b91c1c;
                }
            """)
            btn_kill.clicked.connect(self.accept)
            btn_layout.addWidget(btn_kill)

        layout.addLayout(btn_layout)
