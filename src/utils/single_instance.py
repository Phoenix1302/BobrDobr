"""
Single-instance application guard for BobrDobr VPN.
Ensures only one instance (Unified across Installed and Portable modes) runs at any time,
preventing severe driver, Wintun adapter, settings and daemon process collisions.
"""

import os
import sys
from typing import Optional
from utils.platform_helper import is_windows


UNIFIED_MUTEX_NAME = "Global\\BobrDobr_VPN_SingleInstance_Unified_v1"
LEGACY_INSTALLED_MUTEX = "Global\\BobrDobr_VPN_SingleInstance_Installed_v1"
LEGACY_PORTABLE_MUTEX = "Global\\BobrDobr_VPN_SingleInstance_Portable_v1"

_SINGLE_INSTANCE_MUTEX = None


def release_single_instance() -> None:
    """
    Closes the global single-instance mutex handle.
    Called on clean application shutdown or immediately before spawning
    an updated/installed executable to prevent startup blocking.
    """
    global _SINGLE_INSTANCE_MUTEX
    if _SINGLE_INSTANCE_MUTEX and is_windows():
        try:
            import ctypes
            ctypes.windll.kernel32.CloseHandle(_SINGLE_INSTANCE_MUTEX)
        except Exception:
            pass
        _SINGLE_INSTANCE_MUTEX = None


def activate_existing_window() -> bool:
    """
    Locates an already running BobrDobr window, restores it from minimized
    or tray state, and brings it to the foreground.
    Uses multi-channel activation:
      1. QLocalSocket IPC to 'BobrDobr_VPN_SingleInstance_IPC' (triggers Qt showNormal directly in main thread)
      2. Windows Registered Window Message (WM_BOBRDOBR_ACTIVATE)
      3. Win32 EnumWindows with AttachThreadInput foreground lock bypass and SW_RESTORE
    """
    activated = False

    # Channel 1: QLocalSocket IPC (wakes up Qt event loop and restores window from tray)
    try:
        from PySide6.QtNetwork import QLocalSocket
        sock = QLocalSocket()
        sock.connectToServer("BobrDobr_VPN_SingleInstance_IPC")
        if sock.waitForConnected(600):
            sock.write(b"ACTIVATE\n")
            sock.flush()
            sock.waitForBytesWritten(600)
            sock.disconnectFromServer()
            activated = True
    except Exception:
        pass

    # Channel 2 & 3: Win32 message & EnumWindows with AttachThreadInput
    if is_windows():
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            WM_BOBRDOBR_ACTIVATE = user32.RegisterWindowMessageW("BobrDobr_VPN_Activate_Window_Msg")
            # Broadcast message to top-level windows
            user32.PostMessageW(0xFFFF, WM_BOBRDOBR_ACTIVATE, 0, 0)

            def is_bobrdobr_window(h) -> bool:
                try:
                    target_pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(h, ctypes.byref(target_pid))
                    pid = target_pid.value
                    if pid == 0 or pid == os.getpid():
                        return False

                    # 1. Process image name check - strictly isolate to BobrDobr process
                    h_proc = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
                    if not h_proc:
                        return False
                    try:
                        path_buf = ctypes.create_unicode_buffer(1024)
                        size = wintypes.DWORD(1024)
                        if not kernel32.QueryFullProcessImageNameW(h_proc, 0, path_buf, ctypes.byref(size)):
                            return False
                        exe_name = os.path.basename(path_buf.value).lower()
                    finally:
                        kernel32.CloseHandle(h_proc)

                    # Strictly exclude web browsers, code editors and developer tools
                    if any(b in exe_name for b in ("chrome", "msedge", "firefox", "opera", "brave", "yandex", "code", "devenv")):
                        return False

                    # Must be BobrDobr client executable (or python in development environment)
                    if "bobrdobr" not in exe_name and "python" not in exe_name:
                        return False

                    # 2. Window class check - browsers use Chrome_WidgetWin_1, MozillaWindowClass, etc.
                    class_buf = ctypes.create_unicode_buffer(256)
                    user32.GetClassNameW(h, class_buf, 256)
                    class_name = class_buf.value
                    if any(c in class_name for c in ("Chrome", "Mozilla", "ApplicationFrameWindow")):
                        return False

                    # 3. Window title check
                    length = user32.GetWindowTextLengthW(h)
                    if length <= 0:
                        return False
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(h, buff, length + 1)
                    title = buff.value

                    # Must NOT be browser dashboard or web panel tab
                    if any(ign in title for ign in ("Панель управления", "dashboard", "Visual Studio", "Visual Studio Code", "Browser")):
                        return False

                    # Must contain БобрДобр
                    return "БобрДобр" in title
                except Exception:
                    return False

            def enum_cb(h, _):
                nonlocal activated
                if is_bobrdobr_window(h):
                    user32.PostMessageW(h, WM_BOBRDOBR_ACTIVATE, 0, 0)

                    fore_hwnd = user32.GetForegroundWindow()
                    fore_thread = user32.GetWindowThreadProcessId(fore_hwnd, None)
                    cur_thread = kernel32.GetCurrentThreadId()

                    user32.ShowWindow(h, 9)  # SW_RESTORE
                    user32.BringWindowToTop(h)

                    if fore_thread != cur_thread:
                        user32.AttachThreadInput(cur_thread, fore_thread, True)
                        user32.SetForegroundWindow(h)
                        user32.AttachThreadInput(cur_thread, fore_thread, False)
                    else:
                        user32.SetForegroundWindow(h)

                    activated = True
                    return False
                return True

            WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
        except Exception:
            pass

    return activated


def show_already_running_message() -> None:
    """
    Displays a modal top-most Win32 notification notifying the user that BobrDobr VPN
    is already running and dual execution has been safely intercepted.
    """
    if not is_windows():
        return
    try:
        import ctypes
        user32 = ctypes.windll.user32
        MB_OK = 0x00000000
        MB_ICONINFORMATION = 0x00000040
        MB_SETFOREGROUND = 0x00010000
        MB_TOPMOST = 0x00040000
        msg = (
            "БобрДобр VPN уже запущен на вашем компьютере.\n\n"
            "Одновременная работа нескольких экземпляров (Portable и Установленной версии) "
            "заблокирована во избежание конфликтов виртуального адаптера Wintun, портов "
            "и повреждения файлов конфигурации.\n\n"
            "Активное окно программы выведено на передний план."
        )
        title = "БобрДобр VPN — Экземпляр уже активен"
        user32.MessageBoxW(0, msg, title, MB_OK | MB_ICONINFORMATION | MB_SETFOREGROUND | MB_TOPMOST)
    except Exception:
        pass


def check_single_instance(show_dialog: bool = False) -> bool:
    """
    Checks if this is the only active BobrDobr VPN process.
    Uses UNIFIED mutex across Installed and Portable versions.
    If another instance is detected:
      1. Activates existing window.
      2. Shows user alert (if show_dialog is True).
      3. Returns False.
    Returns True if mutex was successfully acquired.
    """
    global _SINGLE_INSTANCE_MUTEX
    if not is_windows():
        return True

    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        ERROR_ALREADY_EXISTS = 183

        # 1. Acquire Unified Single-Instance Mutex
        h_mutex = kernel32.CreateMutexW(None, False, UNIFIED_MUTEX_NAME)
        if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            if h_mutex:
                kernel32.CloseHandle(h_mutex)
            is_duplicate = True
        else:
            _SINGLE_INSTANCE_MUTEX = h_mutex
            is_duplicate = False

        # 2. Check legacy mutex names for backward compatibility with older running builds
        if not is_duplicate:
            SYNCHRONIZE = 0x00100000
            for legacy_name in (LEGACY_INSTALLED_MUTEX, LEGACY_PORTABLE_MUTEX):
                h_legacy = kernel32.OpenMutexW(SYNCHRONIZE, False, legacy_name)
                if h_legacy:
                    kernel32.CloseHandle(h_legacy)
                    is_duplicate = True
                    break

        if is_duplicate:
            activate_existing_window()
            if show_dialog:
                show_already_running_message()
            return False

        return True
    except Exception:
        return True
