"""GUI module for VPN Desktop Launcher."""
from gui.styles import DARK_THEME_QSS, get_stylesheet
from gui.log_viewer import LogViewer
from gui.tab_amnezia import AmneziaTab
from gui.tab_openconnect import OpenConnectTab
from gui.installer_dialog import InstallDialog, UninstallDialog, UpdateDialog

__all__ = ["DARK_THEME_QSS", "get_stylesheet", "LogViewer", "AmneziaTab", "OpenConnectTab", "InstallDialog", "UninstallDialog", "UpdateDialog"]
