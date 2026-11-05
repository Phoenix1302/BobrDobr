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


def _create_mutex_security_attributes():
    """
    Creates a Win32 SECURITY_ATTRIBUTES struct with SDDL:
    'D:(A;;GA;;;WD)S:(ML;;NW;;;LW)'
      - DACL: World/Everyone (WD) has Generic All (GA)
      - SACL: Mandatory Integrity Label at Low Level (LW) with No-Write-Up (NW) policy
    This permits cross-integrity level access between Standard User (Medium Integrity)
    and Administrator (High Integrity).

    If SDDL string conversion fails, falls back to a SECURITY_DESCRIPTOR with
    SetSecurityDescriptorDacl(pSD, True, None, False) (NULL DACL granting unrestricted access).

    Returns:
        tuple (sa_pointer_or_struct, cleanup_callback)
    """
    if not is_windows():
        return None, None

    try:
        import ctypes
        from ctypes import wintypes

        class SECURITY_ATTRIBUTES(ctypes.Structure):
            _fields_ = [
                ("nLength", wintypes.DWORD),
                ("lpSecurityDescriptor", wintypes.LPVOID),
                ("bInheritHandle", wintypes.BOOL),
            ]

        advapi32 = ctypes.windll.advapi32
        kernel32 = ctypes.windll.kernel32

        # 1. Primary: SDDL with Low Mandatory Label and Everyone Generic All
        SDDL_REVISION_1 = 1
        sddl = "D:(A;;GA;;;WD)S:(ML;;NW;;;LW)"
        p_sd = wintypes.LPVOID()
        sd_size = wintypes.ULONG()

        advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.LPVOID),
            ctypes.POINTER(wintypes.ULONG),
        ]
        advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL

        if advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl, SDDL_REVISION_1, ctypes.byref(p_sd), ctypes.byref(sd_size)
        ) and p_sd.value:
            sa = SECURITY_ATTRIBUTES()
            sa.nLength = ctypes.sizeof(SECURITY_ATTRIBUTES)
            sa.lpSecurityDescriptor = p_sd
            sa.bInheritHandle = False

            def cleanup_sddl():
                try:
                    kernel32.LocalFree(p_sd)
                except Exception:
                    pass

            return sa, cleanup_sddl
    except Exception:
        pass

    # 2. Fallback: InitializeSecurityDescriptor + SetSecurityDescriptorDacl with NULL DACL
    try:
        import ctypes
        from ctypes import wintypes

        class SECURITY_ATTRIBUTES(ctypes.Structure):
            _fields_ = [
                ("nLength", wintypes.DWORD),
                ("lpSecurityDescriptor", wintypes.LPVOID),
                ("bInheritHandle", wintypes.BOOL),
            ]

        advapi32 = ctypes.windll.advapi32
        sd_buf = ctypes.create_string_buffer(64)

        advapi32.InitializeSecurityDescriptor.argtypes = [wintypes.LPVOID, wintypes.DWORD]
        advapi32.InitializeSecurityDescriptor.restype = wintypes.BOOL
        advapi32.SetSecurityDescriptorDacl.argtypes = [
            wintypes.LPVOID,
            wintypes.BOOL,
            wintypes.LPVOID,
            wintypes.BOOL,
        ]
        advapi32.SetSecurityDescriptorDacl.restype = wintypes.BOOL

        if advapi32.InitializeSecurityDescriptor(sd_buf, 1) and advapi32.SetSecurityDescriptorDacl(
            sd_buf, True, None, False
        ):
            sa = SECURITY_ATTRIBUTES()
            sa.nLength = ctypes.sizeof(SECURITY_ATTRIBUTES)
            sa.lpSecurityDescriptor = ctypes.cast(sd_buf, wintypes.LPVOID)
            sa.bInheritHandle = False
            return sa, lambda: None
    except Exception:
        pass

    return None, None


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
      3. Win32 EnumWindows with Alt-key focus lock bypass and SW_RESTORE
    """
    # Grant permission to the existing instance process to take foreground focus
    if is_windows():
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            try:
                user32.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
                user32.AllowSetForegroundWindow.restype = wintypes.BOOL
            except Exception:
                pass
            user32.AllowSetForegroundWindow(0xFFFFFFFF)
        except Exception:
            pass

    # Channel 1: QLocalSocket IPC (wakes up Qt event loop and restores window from tray)
    try:
        from PySide6.QtNetwork import QLocalSocket
        sock = QLocalSocket()
        sock.connectToServer("BobrDobr_VPN_SingleInstance_IPC")
        if sock.waitForConnected(700):
            sock.write(b"ACTIVATE\n")
            sock.waitForBytesWritten(700)
            try:
                sock.disconnectFromServer()
            except Exception:
                pass
            return True
    except Exception:
        pass

    # Channel 2 & 3: Win32 message & EnumWindows fallback
    if is_windows():
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            WM_BOBRDOBR_ACTIVATE = user32.RegisterWindowMessageW("BobrDobr_VPN_Activate_Window_Msg")
            HWND_BROADCAST = 0xFFFF
            # Broadcast message to top-level windows
            user32.PostMessageW(HWND_BROADCAST, WM_BOBRDOBR_ACTIVATE, 0, 0)

            def is_bobrdobr_window(h) -> bool:
                try:
                    target_pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(h, ctypes.byref(target_pid))
                    pid = target_pid.value
                    if pid == 0 or pid == os.getpid():
                        return False

                    # 1. Process image name check - strictly isolate to BobrDobr process
                    h_proc = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
                    if h_proc:
                        try:
                            path_buf = ctypes.create_unicode_buffer(1024)
                            size = wintypes.DWORD(1024)
                            if kernel32.QueryFullProcessImageNameW(h_proc, 0, path_buf, ctypes.byref(size)):
                                exe_name = os.path.basename(path_buf.value).lower()
                                # Strictly exclude web browsers, code editors, file explorer and developer tools
                                if any(b in exe_name for b in ("chrome", "msedge", "firefox", "opera", "brave", "yandex", "code", "devenv", "explorer")):
                                    return False
                                # Must be BobrDobr client executable (or python in development environment)
                                if "bobrdobr" not in exe_name and "python" not in exe_name:
                                    return False
                        finally:
                            kernel32.CloseHandle(h_proc)

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

            activated = False
            def enum_cb(h, _):
                nonlocal activated
                if is_bobrdobr_window(h):
                    target_pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(h, ctypes.byref(target_pid))
                    if target_pid.value:
                        try:
                            user32.AllowSetForegroundWindow(target_pid.value)
                        except Exception:
                            pass

                    user32.PostMessageW(h, WM_BOBRDOBR_ACTIVATE, 0, 0)
                    user32.ShowWindow(h, 9)  # SW_RESTORE
                    user32.BringWindowToTop(h)
                    # Use Alt-key trick to cleanly bypass Windows foreground lock without attaching to other threads
                    user32.keybd_event(0x12, 0, 0, 0)  # VK_MENU down
                    user32.SetForegroundWindow(h)
                    user32.keybd_event(0x12, 0, 2, 0)  # VK_MENU up

                    activated = True
                    return False
                return True

            WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
            return activated
        except Exception:
            pass

    return False


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
    Uses UNIFIED mutex across Installed and Portable versions with cross-integrity
    Win32 security attributes (allowing seamless coexistence between Standard User and Administrator).
    If another instance is detected:
      1. Activates existing window.
      2. Shows user alert (if show_dialog is True).
      3. Returns False.
    Returns True if mutex was successfully acquired.
    """
    global _SINGLE_INSTANCE_MUTEX
    if not is_windows():
        return True

    sa, cleanup = _create_mutex_security_attributes()
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        ERROR_ACCESS_DENIED = 5
        ERROR_ALREADY_EXISTS = 183

        # 1. Acquire Unified Single-Instance Mutex with cross-integrity attributes
        p_sa = ctypes.byref(sa) if sa else None
        h_mutex = kernel32.CreateMutexW(p_sa, False, UNIFIED_MUTEX_NAME)
        last_err = kernel32.GetLastError()

        if last_err in (ERROR_ALREADY_EXISTS, ERROR_ACCESS_DENIED):
            if h_mutex:
                kernel32.CloseHandle(h_mutex)
            is_duplicate = True
        elif h_mutex:
            _SINGLE_INSTANCE_MUTEX = h_mutex
            is_duplicate = False
        else:
            # Handle is 0/NULL: inspect error
            if last_err in (ERROR_ALREADY_EXISTS, ERROR_ACCESS_DENIED):
                is_duplicate = True
            else:
                is_duplicate = False

        # 2. Check legacy mutex names for backward compatibility with older running builds
        if not is_duplicate:
            SYNCHRONIZE = 0x00100000
            for legacy_name in (LEGACY_INSTALLED_MUTEX, LEGACY_PORTABLE_MUTEX):
                h_legacy = kernel32.OpenMutexW(SYNCHRONIZE, False, legacy_name)
                legacy_err = kernel32.GetLastError()
                if h_legacy:
                    kernel32.CloseHandle(h_legacy)
                    is_duplicate = True
                    break
                elif legacy_err in (ERROR_ALREADY_EXISTS, ERROR_ACCESS_DENIED):
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
    finally:
        if cleanup:
            cleanup()
