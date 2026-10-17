from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QPlainTextEdit, QCheckBox, QApplication
)
from PySide6.QtGui import QTextCursor
from PySide6.QtCore import Qt


class LogViewer(QWidget):
    """
    Бортовой журнал плотины БобрДобр.
    Выдвижная консоль логов с цветовой дифференциацией потоков,
    автоскроллом и возможностью копирования записей.
    """

    MAX_LOG_LINES = 1000

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_collapsed = True
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(6)

        # Панель управления журналом
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(10)

        from PySide6.QtWidgets import QLabel
        log_title = QLabel("📋 Бортовой журнал плотины")
        log_title.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 700;")
        header_layout.addWidget(log_title)

        header_layout.addStretch()

        self.autoscroll_cb = QCheckBox("Следить за течением")
        self.autoscroll_cb.setChecked(True)
        self.autoscroll_cb.setCursor(Qt.PointingHandCursor)
        header_layout.addWidget(self.autoscroll_cb)

        self.copy_btn = QPushButton("Копировать")
        self.copy_btn.setObjectName("btn_secondary")
        self.copy_btn.setCursor(Qt.PointingHandCursor)
        self.copy_btn.setFixedHeight(26)
        self.copy_btn.clicked.connect(self.copy_to_clipboard)
        header_layout.addWidget(self.copy_btn)

        self.clear_btn = QPushButton("Очистить")
        self.clear_btn.setObjectName("btn_secondary")
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.setFixedHeight(26)
        self.clear_btn.clicked.connect(self.clear_logs)
        header_layout.addWidget(self.clear_btn)

        layout.addLayout(header_layout)

        # Текстовое поле консоли
        self.text_area = QPlainTextEdit()
        self.text_area.setReadOnly(True)
        self.text_area.setFixedHeight(180)
        layout.addWidget(self.text_area)

    def append_log(self, text: str, channel: str = "stdout"):
        """Добавляет стилизованную запись в бортовой журнал плотины."""
        channel_info = {
            "stdout": ("ПОТОК", "#cbd5e1"),
            "stderr": ("ВОДОВОРОТ", "#fbbf24"),
            "sys": ("БОБР", "#d97706"),
            "error": ("ПРОТЕЧКА", "#f87171")
        }
        tag, color = channel_info.get(channel, ("ИНФО", "#94a3b8"))
        html_msg = f'<span style="color: {color};"><strong>[{tag}]</strong> {self._escape_html(text)}</span>'

        self.text_area.appendHtml(html_msg)

        doc = self.text_area.document()
        if doc.blockCount() > self.MAX_LOG_LINES:
            cursor = QTextCursor(doc)
            cursor.movePosition(QTextCursor.Start)
            cursor.movePosition(QTextCursor.Down, QTextCursor.KeepAnchor, doc.blockCount() - self.MAX_LOG_LINES)
            cursor.removeSelectedText()

        if self.autoscroll_cb.isChecked():
            self.text_area.moveCursor(QTextCursor.End)

    def clear_logs(self):
        self.text_area.clear()

    def copy_to_clipboard(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.text_area.toPlainText())

    @staticmethod
    def _escape_html(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
