"""
БобрДобр (BobrDobr) Refined Hydro-Engineering Dark Theme for PySide6.
Visual fixes: clean font rendering without emoji tofu boxes,
polished input fields, responsive grids, crisp status badges,
and robust dark theme for all dialogs, popups and message boxes.
"""
import os
from utils.platform_helper import get_base_dir

_BASE_THEME_QSS = """
QMainWindow, QDialog, QMessageBox, QFileDialog {
    background-color: #0c1316;
    color: #e2e8f0;
}

QWidget {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI Variable Text", "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
    color: #e2e8f0;
}

/* System Dialogs & Message Boxes */
QMessageBox {
    background-color: #0f1416;
    color: #e2e8f0;
}

QMessageBox QLabel {
    color: #f8fafc;
    font-size: 13px;
    background-color: transparent;
    padding: 4px;
}

QMessageBox QPushButton {
    background-color: #1a252a;
    color: #f1f5f9;
    border: 1px solid #334852;
    min-width: 80px;
    padding: 6px 16px;
    font-size: 12px;
    font-weight: 600;
    border-radius: 6px;
}

QMessageBox QPushButton:hover {
    background-color: #24343b;
    border-color: #d97706;
    color: #ffffff;
}

QMessageBox QPushButton:default {
    background-color: #d97706;
    border-color: #b45309;
    color: #ffffff;
}

QMessageBox QPushButton:default:hover {
    background-color: #b45309;
}

QDialogButtonBox {
    background-color: transparent;
}

/* Tooltips & Context Menus */
QToolTip {
    background-color: #141c22;
    color: #f8fafc;
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 12px;
}

QMenu {
    background-color: #141c22;
    color: #f1f5f9;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-top: 1px solid rgba(255, 255, 255, 0.22);
    border-radius: 10px;
    padding: 6px;
}

QMenu::item {
    font-size: 13px;
    font-weight: 600;
    padding: 8px 18px 8px 14px;
    border-radius: 6px;
    margin: 2px 2px;
    color: #e2e8f0;
}

QMenu::item:selected {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #d97706, stop:1 #b45309);
    color: #ffffff;
}

QMenu::separator {
    height: 1px;
    background-color: rgba(255, 255, 255, 0.08);
    margin: 6px 8px;
}

QMenu::item:disabled {
    color: #64748b;
    background-color: transparent;
    font-size: 12px;
    font-weight: 500;
}

/* Group Boxes / Volumetric Dialog Cards */
QGroupBox {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #18232a, stop:1 #0f161a);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-top: 1px solid rgba(255, 255, 255, 0.18);
    border-radius: 12px;
    margin-top: 20px;
    padding: 20px 16px 14px 16px;
    font-weight: 700;
    color: #e2e8f0;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    top: 4px;
    padding: 3px 12px;
    background-color: #1a252c;
    border: 1px solid rgba(217, 119, 6, 0.35);
    border-radius: 6px;
    color: #f59e0b;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 0.3px;
}

/* VPN Profile Card - Modern Volumetric Floating Surfaces (Matching Bottom Dock) */
#vpn_profile_card, QFrame#vpn_profile_card {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #18232a, stop:1 #0f161a);
    border: 1px solid rgba(255, 255, 255, 0.09);
    border-top: 1px solid rgba(255, 255, 255, 0.20);
    border-radius: 12px;
}

#vpn_profile_card:hover, QFrame#vpn_profile_card:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1e2c35, stop:1 #131c21);
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-top: 1px solid rgba(255, 255, 255, 0.32);
}

/* Card State: Connected (Active Tunnel) */
#vpn_profile_card[state="connected"], QFrame#vpn_profile_card[state="connected"] {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #18232a, stop:1 #0f161a);
    border: 1px solid rgba(16, 185, 129, 0.50);
    border-top: 1px solid rgba(52, 211, 153, 0.85);
    border-radius: 12px;
}

#vpn_profile_card[state="connected"]:hover, QFrame#vpn_profile_card[state="connected"]:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1e2c35, stop:1 #131c21);
    border: 1px solid rgba(16, 185, 129, 0.70);
    border-top: 1px solid rgba(52, 211, 153, 1.0);
}

/* Card State: Connecting / Reconnecting */
#vpn_profile_card[state="connecting"], QFrame#vpn_profile_card[state="connecting"],
#vpn_profile_card[state="disconnecting"], QFrame#vpn_profile_card[state="disconnecting"] {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #18232a, stop:1 #0f161a);
    border: 1px solid rgba(245, 158, 11, 0.50);
    border-top: 1px solid rgba(251, 191, 36, 0.85);
    border-radius: 12px;
}

#vpn_profile_card[state="connecting"]:hover, QFrame#vpn_profile_card[state="connecting"]:hover,
#vpn_profile_card[state="disconnecting"]:hover, QFrame#vpn_profile_card[state="disconnecting"]:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1e2c35, stop:1 #131c21);
    border: 1px solid rgba(245, 158, 11, 0.70);
    border-top: 1px solid rgba(251, 191, 36, 1.0);
}

/* Card State: Error */
#vpn_profile_card[state="error"], QFrame#vpn_profile_card[state="error"] {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #18232a, stop:1 #0f161a);
    border: 1px solid rgba(239, 68, 68, 0.50);
    border-top: 1px solid rgba(248, 113, 113, 0.85);
    border-radius: 12px;
}

#vpn_profile_card[state="error"]:hover, QFrame#vpn_profile_card[state="error"]:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1e2c35, stop:1 #131c21);
    border: 1px solid rgba(239, 68, 68, 0.70);
    border-top: 1px solid rgba(248, 113, 113, 1.0);
}

/* Form Controls: Full width and clean padding */
QLineEdit, QComboBox, QSpinBox {
    background-color: #0c1215;
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 8px;
    padding: 8px 12px;
    min-height: 22px;
    color: #f8fafc;
    font-size: 13px;
    selection-background-color: #d97706;
}

QLineEdit:hover, QComboBox:hover, QSpinBox:hover {
    border: 1px solid rgba(255, 255, 255, 0.20);
}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border: 1px solid #f59e0b;
    background-color: #10181c;
}

QLineEdit::placeholder {
    color: #64748b;
}

/* QSpinBox Buttons & Modern Clean Arrows */
QSpinBox {
    padding-right: 32px;
}

QSpinBox::up-button, QSpinBox::down-button {
    background-color: #151f24;
    border: none;
    width: 26px;
}

QSpinBox::up-button {
    border-top-right-radius: 7px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

QSpinBox::down-button {
    border-bottom-right-radius: 7px;
}

QSpinBox::up-button:hover, QSpinBox::down-button:hover {
    background-color: #24343d;
}

QSpinBox::up-arrow {
    __SPIN_UP_IMAGE__
    width: 10px;
    height: 10px;
}

QSpinBox::down-arrow {
    __SPIN_DOWN_IMAGE__
    width: 10px;
    height: 10px;
}

/* Form Labels */
QFormLayout QLabel {
    color: #cbd5e1;
    font-size: 13px;
    font-weight: 600;
}

/* ComboBox Styling */
QComboBox {
    padding-right: 32px;
}

QComboBox::drop-down {
    border: none;
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 30px;
    border-left: 1px solid rgba(255, 255, 255, 0.08);
}

QComboBox::drop-down:hover {
    background-color: #1e2c33;
    border-top-right-radius: 7px;
    border-bottom-right-radius: 7px;
}

QComboBox::down-arrow {
    __ARROW_DOWN_IMAGE__
    width: 12px;
    height: 12px;
}

QComboBox QAbstractItemView {
    background-color: #182226;
    color: #f8fafc;
    border: 1px solid #d97706;
    border-radius: 8px;
    selection-background-color: #d97706;
    selection-color: #ffffff;
    padding: 6px;
    outline: none;
}

QComboBox QAbstractItemView::item {
    min-height: 32px;
    padding: 6px 12px;
    color: #f8fafc;
    background-color: #182226;
    border-radius: 4px;
}

QComboBox QAbstractItemView::item:selected {
    background-color: #d97706;
    color: #ffffff;
}

QComboBox QAbstractItemView::item:hover {
    background-color: #24343b;
    color: #ffffff;
}

/* Primary Action Buttons */
QPushButton {
    background-color: #d97706;
    color: #ffffff;
    border: 1px solid #b45309;
    border-radius: 6px;
    padding: 7px 18px;
    font-weight: 700;
}

QPushButton:hover {
    background-color: #f59e0b;
    border-color: #fbbf24;
    color: #ffffff;
}

QPushButton:pressed {
    background-color: #92400e;
    border-color: #78350f;
}

QPushButton:disabled {
    background-color: #1a252a;
    color: #64748b;
    border: 1px solid #24343b;
}

/* Primary Amber Buttons (Create Profile, Save Settings) */
QPushButton#btn_primary {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #d97706, stop:1 #b45309);
    color: #ffffff;
    font-size: 13px;
    font-weight: 700;
    padding: 8px 18px;
    border-radius: 8px;
    border: 1px solid #f59e0b;
}

QPushButton#btn_primary:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #f59e0b, stop:1 #d97706);
    border: 1px solid #fde68a;
    color: #ffffff;
}

QPushButton#btn_primary:pressed {
    background-color: #92400e;
    border: 1px solid #78350f;
}

/* Card Connect Button - Modern Volumetric Emerald Green Accent */
QPushButton#btn_connect {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #10b981, stop:1 #059669);
    color: #ffffff;
    font-size: 13px;
    font-weight: 700;
    padding: 7px 22px;
    border-radius: 8px;
    border: 1px solid rgba(255, 255, 255, 0.16);
    border-bottom: 2px solid #047857;
}

QPushButton#btn_connect:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #34d399, stop:1 #10b981);
    color: #ffffff;
    border: 1px solid rgba(255, 255, 255, 0.28);
    border-bottom: 2px solid #065f46;
}

QPushButton#btn_connect:pressed {
    background-color: #047857;
    border: 1px solid #047857;
}

/* Card Disconnect Button - Translucent Red Effect with Matching Border */
QPushButton#btn_disconnect {
    background-color: rgba(239, 68, 68, 0.12);
    color: #fca5a5;
    font-size: 13px;
    font-weight: 700;
    padding: 7px 22px;
    border-radius: 8px;
    border: 1px solid rgba(239, 68, 68, 0.45);
}

QPushButton#btn_disconnect:hover {
    background-color: rgba(239, 68, 68, 0.28);
    border: 1px solid #ef4444;
    color: #ffffff;
}

QPushButton#btn_disconnect:pressed {
    background-color: rgba(185, 28, 28, 0.55);
    border: 1px solid #dc2626;
    color: #ffffff;
}

/* Connecting / Busy state button - Translucent Amber Glass */
QPushButton#btn_connecting {
    background-color: rgba(217, 119, 6, 0.14);
    color: #fbbf24;
    font-weight: 700;
    font-size: 13px;
    border-radius: 8px;
    border: 1px solid rgba(217, 119, 6, 0.45);
    padding: 7px 22px;
}

/* Secondary Button */
QPushButton#btn_secondary {
    background-color: #1a252a;
    color: #e2e8f0;
    border: 1px solid #283941;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 600;
}

QPushButton#btn_secondary:hover {
    background-color: #24343b;
    color: #f59e0b;
    border-color: #d97706;
}

QPushButton#btn_secondary:pressed {
    background-color: #141c20;
    border-color: #b45309;
}

/* Compact Secondary Buttons (Card Edit, Log Viewer Toggle) */
QPushButton#btn_card_edit {
    background-color: rgba(255, 255, 255, 0.04);
    color: #94a3b8;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 6px;
    padding: 5px 12px;
    font-size: 11px;
    font-weight: 600;
}

QPushButton#btn_card_edit:hover {
    background-color: rgba(217, 119, 6, 0.14);
    color: #f59e0b;
    border-color: rgba(217, 119, 6, 0.35);
}

QPushButton#btn_card_edit:pressed {
    background-color: rgba(217, 119, 6, 0.22);
}

QPushButton#btn_toggle_log {
    background-color: rgba(255, 255, 255, 0.04);
    color: #cbd5e1;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 8px;
    padding: 5px 14px;
    font-size: 11px;
    font-weight: 600;
}

QPushButton#btn_toggle_log:hover {
    background-color: rgba(255, 255, 255, 0.09);
    color: #ffffff;
    border-color: rgba(255, 255, 255, 0.16);
}

QPushButton#btn_toggle_log:pressed {
    background-color: rgba(255, 255, 255, 0.14);
}

/* Danger Card Delete Button */
QPushButton#btn_card_delete {
    background-color: rgba(255, 255, 255, 0.04);
    color: #94a3b8;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 11px;
    font-weight: 600;
}

QPushButton#btn_card_delete:hover {
    background-color: rgba(239, 68, 68, 0.15);
    color: #f87171;
    border-color: rgba(239, 68, 68, 0.35);
}

QPushButton#btn_card_delete:pressed {
    background-color: rgba(239, 68, 68, 0.25);
}

QPushButton#btn_card_delete:pressed {
    background-color: #2b0b0b;
    border-color: #b91c1c;
}

/* Full Destructive Red Button (Dialog Confirmations) */
QPushButton#btn_destructive {
    background-color: #b91c1c;
    border: 1px solid #dc2626;
    color: #ffffff;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 700;
}

QPushButton#btn_destructive:hover {
    background-color: #dc2626;
    border-color: #f87171;
    color: #ffffff;
}

QPushButton#btn_destructive:pressed {
    background-color: #991b1b;
    border-color: #7f1d1d;
}

/* PlainTextEdit (Logs and Config viewer) */
QPlainTextEdit {
    background-color: #0a0e10;
    border: 1px solid #24343b;
    border-radius: 6px;
    font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
    font-size: 12px;
    color: #cbd5e1;
    padding: 8px;
}

/* AWG Config Editor Block with Integrated Footer Status Bar */
QFrame#awg_editor_container {
    background-color: #0a0e10;
    border: 1px solid #24343b;
    border-radius: 8px;
}

QFrame#awg_editor_container:hover {
    border-color: #3b505c;
}

QFrame#awg_editor_container:focus-within {
    border-color: #f59e0b;
}

QFrame#awg_editor_container QPlainTextEdit {
    background-color: transparent;
    border: none;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    border-bottom-left-radius: 0px;
    border-bottom-right-radius: 0px;
    padding: 8px 10px;
}

QFrame#awg_status_footer {
    background-color: #0c1215;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
    border-bottom-left-radius: 7px;
    border-bottom-right-radius: 7px;
    min-height: 28px;
}

QFrame#awg_status_footer QLabel {
    background-color: transparent;
}

/* Scrollbars */
QScrollBar:vertical {
    border: none;
    background: #0f1416;
    width: 8px;
    margin: 0px;
    border-radius: 4px;
}

QScrollBar::handle:vertical {
    background: #24343b;
    min-height: 24px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #d97706;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
    background: none;
}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
}

QScrollBar:horizontal {
    border: none;
    background: #0f1416;
    height: 8px;
    margin: 0px;
    border-radius: 4px;
}

QScrollBar::handle:horizontal {
    background: #24343b;
    min-width: 24px;
    border-radius: 4px;
}

QScrollBar::handle:horizontal:hover {
    background: #d97706;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
    background: none;
}

QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: none;
}

/* Checkbox */
QCheckBox {
    color: #cbd5e1;
    spacing: 8px;
}

QCheckBox:disabled {
    color: #64748b;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid #33454e;
    background: #0f1416;
}

QCheckBox::indicator:hover {
    border-color: #d97706;
}

QCheckBox::indicator:pressed {
    background-color: #1a252a;
    border-color: #b45309;
}

QCheckBox::indicator:checked {
    background: #d97706;
    border-color: #f59e0b;
    __CHECK_IMAGE__
}

QCheckBox::indicator:checked:hover {
    background: #b45309;
    border-color: #d97706;
}

QCheckBox::indicator:disabled {
    background: #141b1f;
    border-color: #24343b;
}

QCheckBox::indicator:checked:disabled {
    background: #78350f;
    border-color: #92400e;
}

/* Radio Button */
QRadioButton {
    color: #cbd5e1;
    spacing: 8px;
}

QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border-radius: 9px;
    border: 1px solid #33454e;
    background: #0f1416;
}

QRadioButton::indicator:hover {
    border-color: #d97706;
}

QRadioButton::indicator:checked {
    background: #d97706;
    border: 3px solid #0f1416;
}

/* Install / Installed / Uninstall Header Badges */
QPushButton#btn_install_badge {
    background-color: rgba(56, 189, 248, 0.10);
    color: #38bdf8;
    border: 1px solid rgba(56, 189, 248, 0.35);
    border-radius: 14px;
    padding: 5px 14px;
    font-size: 11px;
    font-weight: 700;
}

QPushButton#btn_install_badge:hover {
    background-color: rgba(56, 189, 248, 0.20);
    color: #ffffff;
    border-color: #38bdf8;
}

QPushButton#btn_installed_badge, QPushButton#btn_uninstall_badge {
    background-color: rgba(255, 255, 255, 0.04);
    color: #94a3b8;
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 14px;
    padding: 5px 14px;
    font-size: 11px;
    font-weight: 700;
}

QPushButton#btn_installed_badge:hover, QPushButton#btn_uninstall_badge:hover {
    background-color: rgba(239, 68, 68, 0.15);
    color: #f87171;
    border-color: rgba(239, 68, 68, 0.40);
}

/* Status Badges */
QLabel#status_pill {
    padding: 4px 14px;
    border-radius: 12px;
    font-weight: 800;
    font-size: 11px;
}

/* Scroll Area for Profiles */
QScrollArea {
    border: none;
    background-color: transparent;
}

QScrollArea > QWidget > QWidget {
    background-color: transparent;
}
"""


def resolve_check_icon_path() -> str:
    """Finds the checkmark icon file across frozen bundle and source paths."""
    candidates = [
        os.path.join(get_base_dir(), "assets", "check.png"),
        os.path.join(get_base_dir(), "src", "assets", "check.png"),
        os.path.join(os.path.dirname(__file__), "..", "assets", "check.png"),
        os.path.join(get_base_dir(), "assets", "check.svg"),
        os.path.join(get_base_dir(), "src", "assets", "check.svg"),
        os.path.join(os.path.dirname(__file__), "..", "assets", "check.svg"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return os.path.abspath(c).replace("\\", "/")
    return ""


def resolve_arrow_icon_path() -> str:
    """Finds the dropdown arrow icon file across frozen bundle and source paths."""
    candidates = [
        os.path.join(get_base_dir(), "assets", "arrow_down.svg"),
        os.path.join(get_base_dir(), "src", "assets", "arrow_down.svg"),
        os.path.join(os.path.dirname(__file__), "..", "assets", "arrow_down.svg"),
        os.path.join(get_base_dir(), "assets", "arrow_down.png"),
        os.path.join(get_base_dir(), "src", "assets", "arrow_down.png"),
        os.path.join(os.path.dirname(__file__), "..", "assets", "arrow_down.png"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return os.path.abspath(c).replace("\\", "/")
    return ""


def resolve_spin_up_icon_path() -> str:
    """Finds the spinbox up arrow icon across bundle and source paths."""
    candidates = [
        os.path.join(get_base_dir(), "assets", "spin_up.svg"),
        os.path.join(get_base_dir(), "src", "assets", "spin_up.svg"),
        os.path.join(os.path.dirname(__file__), "..", "assets", "spin_up.svg"),
        os.path.join(os.path.dirname(__file__), "assets", "spin_up.svg"),
        os.path.join(os.getcwd(), "assets", "spin_up.svg"),
        os.path.join(os.getcwd(), "src", "assets", "spin_up.svg"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return os.path.abspath(c).replace("\\", "/")
    return ""


def resolve_spin_down_icon_path() -> str:
    """Finds the spinbox down arrow icon across bundle and source paths."""
    candidates = [
        os.path.join(get_base_dir(), "assets", "spin_down.svg"),
        os.path.join(get_base_dir(), "src", "assets", "spin_down.svg"),
        os.path.join(os.path.dirname(__file__), "..", "assets", "spin_down.svg"),
        os.path.join(os.path.dirname(__file__), "assets", "spin_down.svg"),
        os.path.join(os.getcwd(), "assets", "spin_down.svg"),
        os.path.join(os.getcwd(), "src", "assets", "spin_down.svg"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return os.path.abspath(c).replace("\\", "/")
    return ""


def resolve_amnezia_icon_path() -> str:
    """Finds the AmneziaWG SVG icon across frozen bundle and source paths."""
    candidates = [
        os.path.join(get_base_dir(), "assets", "amnezia.svg"),
        os.path.join(get_base_dir(), "src", "assets", "amnezia.svg"),
        os.path.join(os.path.dirname(__file__), "..", "assets", "amnezia.svg"),
        os.path.join(os.path.dirname(__file__), "assets", "amnezia.svg"),
        os.path.join(os.getcwd(), "assets", "amnezia.svg"),
        os.path.join(os.getcwd(), "src", "assets", "amnezia.svg"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return os.path.abspath(c).replace("\\", "/")
    return ""


def resolve_openconnect_icon_path() -> str:
    """Finds the OpenConnect SVG icon across frozen bundle and source paths."""
    candidates = [
        os.path.join(get_base_dir(), "assets", "openconnect.svg"),
        os.path.join(get_base_dir(), "src", "assets", "openconnect.svg"),
        os.path.join(os.path.dirname(__file__), "..", "assets", "openconnect.svg"),
        os.path.join(os.path.dirname(__file__), "assets", "openconnect.svg"),
        os.path.join(os.getcwd(), "assets", "openconnect.svg"),
        os.path.join(os.getcwd(), "src", "assets", "openconnect.svg"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return os.path.abspath(c).replace("\\", "/")
    return ""


def get_amnezia_icon():
    from PySide6.QtGui import QIcon
    p = resolve_amnezia_icon_path()
    return QIcon(p) if p else QIcon()


def get_openconnect_icon():
    from PySide6.QtGui import QIcon
    p = resolve_openconnect_icon_path()
    return QIcon(p) if p else QIcon()


def get_amnezia_pixmap(width: int = 16, height: int = 16):
    from PySide6.QtCore import QSize
    icon = get_amnezia_icon()
    return icon.pixmap(QSize(width, height))


def get_openconnect_pixmap(width: int = 16, height: int = 16):
    from PySide6.QtCore import QSize
    icon = get_openconnect_icon()
    return icon.pixmap(QSize(width, height))


def get_stylesheet() -> str:
    """Returns the complete dark stylesheet with resolved checkmark and arrow icon assets."""
    icon_path = resolve_check_icon_path()
    check_image = f'image: url("{icon_path}");' if icon_path else ""

    arrow_path = resolve_arrow_icon_path()
    arrow_image = f'image: url("{arrow_path}");' if arrow_path else ""

    spin_up_path = resolve_spin_up_icon_path()
    spin_up_image = f'image: url("{spin_up_path}");' if spin_up_path else ""

    spin_down_path = resolve_spin_down_icon_path()
    spin_down_image = f'image: url("{spin_down_path}");' if spin_down_path else ""

    qss = _BASE_THEME_QSS.replace("__CHECK_IMAGE__", check_image)
    qss = qss.replace("__ARROW_DOWN_IMAGE__", arrow_image)
    qss = qss.replace("__SPIN_UP_IMAGE__", spin_up_image)
    qss = qss.replace("__SPIN_DOWN_IMAGE__", spin_down_image)
    return qss


DARK_THEME_QSS = get_stylesheet()

