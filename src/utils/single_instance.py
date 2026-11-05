"""
Single-instance application guard and process manager for BobrDobr VPN.
Ensures only one instance (Unified across Installed and Portable modes) runs at any time,
preventing severe driver, Wintun adapter, settings and daemon process collisions.

Provides interactive process conflict resolution, ghost/hung background process termination
(with automatic UAC escalation when needed), and clean IPC communication.
"""

import os
import sys
import time
from typing import Optional, List, Dict, Any
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
    Called on clean application shutdown, before updating, or after terminating
    a colliding instance to allow re-acquisition.
    """
    global _SINGLE_INSTANCE_MUTEX
    if _SINGLE_INSTANCE_MUTEX and is_windows():
        try:
            import ctypes
            ctypes.windll.kernel32.CloseHandle(_SINGLE_INSTANCE_MUTEX)
        except Exception:
            pass
        _SINGLE_INSTANCE_MUTEX = None


def try_acquire_single_instance() -> bool:
    """
    Attempts to acquire the unified single instance mutex with cross-integrity attributes.
    Also inspects legacy mutexes for backward compatibility.
    Returns True if successfully acquired and no duplicate is running, False otherwise.
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

        p_sa = ctypes.byref(sa) if sa else None
        h_mutex = kernel32.CreateMutexW(p_sa, False, UNIFIED_MUTEX_NAME)
        last_err = kernel32.GetLastError()

        if last_err in (ERROR_ALREADY_EXISTS, ERROR_ACCESS_DENIED):
            if h_mutex:
                kernel32.CloseHandle(h_mutex)
            return False
        elif h_mutex:
            _SINGLE_INSTANCE_MUTEX = h_mutex
        else:
            if last_err in (ERROR_ALREADY_EXISTS, ERROR_ACCESS_DENIED):
                return False

        # Inspect legacy mutex names
        SYNCHRONIZE = 0x00100000
        for legacy_name in (LEGACY_INSTALLED_MUTEX, LEGACY_PORTABLE_MUTEX):
            h_legacy = kernel32.OpenMutexW(SYNCHRONIZE, False, legacy_name)
            legacy_err = kernel32.GetLastError()
            if h_legacy:
                kernel32.CloseHandle(h_legacy)
                release_single_instance()
                return False
            elif legacy_err in (ERROR_ALREADY_EXISTS, ERROR_ACCESS_DENIED):
                release_single_instance()
                return False

        return True
    except Exception:
        return True
    finally:
        if cleanup:
            cleanup()


def activate_existing_window() -> bool:
    """
    Locates an already running BobrDobr window, restores it from minimized
    or tray state, and brings it to the foreground.
    Uses multi-channel activation:
      1. QLocalSocket IPC to 'BobrDobr_VPN_SingleInstance_IPC' (triggers Qt showNormal directly in main thread)
      2. Windows Registered Window Message (WM_BOBRDOBR_ACTIVATE)
      3. Win32 EnumWindows with Alt-key focus lock bypass and SW_RESTORE
    Returns True if an existing window/service was successfully activated.
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
        if sock.waitForConnected(600):
            sock.write(b"ACTIVATE\n")
            sock.waitForBytesWritten(600)
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
                                if any(b in exe_name for b in ("chrome", "msedge", "firefox", "opera", "brave", "yandex", "code", "devenv", "explorer")):
                                    return False
                                if "bobrdobr" not in exe_name and "python" not in exe_name:
                                    return False
                        finally:
                            kernel32.CloseHandle(h_proc)

                    # 2. Window class check
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

                    if any(ign in title for ign in ("Панель управления", "dashboard", "Visual Studio", "Visual Studio Code", "Browser")):
                        return False

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
    Backward-compatible single instance check.
    Returns True if mutex was successfully acquired, False otherwise.
    """
    is_acquired = try_acquire_single_instance()
    if not is_acquired:
        activate_existing_window()
        if show_dialog:
            show_already_running_message()
        return False
    return True


def find_other_bobrdobr_processes() -> List[Dict[str, Any]]:
    """
    Scans running processes and returns a list of other BobrDobr VPN processes
    (Installed or Portable, active or hanging in background).
    Excludes the current process PID.
    """
    if not is_windows():
        return []

    results = []
    try:
        import ctypes
        from ctypes import wintypes

        TH32CS_SNAPPROCESS = 0x00000002

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [
                ('dwSize', wintypes.DWORD),
                ('cntUsage', wintypes.DWORD),
                ('th32ProcessID', wintypes.DWORD),
                ('th32DefaultHeapID', ctypes.c_size_t),
                ('th32ModuleID', wintypes.DWORD),
                ('cntThreads', wintypes.DWORD),
                ('th32ParentProcessID', wintypes.DWORD),
                ('pcPriClassBase', wintypes.LONG),
                ('dwFlags', wintypes.DWORD),
                ('szExeFile', wintypes.WCHAR * 260)
            ]

        kernel32 = ctypes.windll.kernel32
        h_snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
        if not h_snap or h_snap == INVALID_HANDLE_VALUE:
            return []

        pe = PROCESSENTRY32W()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)

        kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
        kernel32.Process32FirstW.restype = wintypes.BOOL
        kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
        kernel32.Process32NextW.restype = wintypes.BOOL

        my_pid = os.getpid()
        if kernel32.Process32FirstW(h_snap, ctypes.byref(pe)):
            while True:
                pid = pe.th32ProcessID
                exe_name = pe.szExeFile.lower()
                if pid != my_pid and pid > 0:
                    matched = False
                    if "bobrdobr" in exe_name:
                        matched = True

                    if matched:
                        exe_path = ""
                        h_proc = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
                        if h_proc:
                            try:
                                path_buf = ctypes.create_unicode_buffer(1024)
                                size = wintypes.DWORD(1024)
                                if kernel32.QueryFullProcessImageNameW(h_proc, 0, path_buf, ctypes.byref(size)):
                                    exe_path = path_buf.value
                            finally:
                                kernel32.CloseHandle(h_proc)

                        p_lower = (exe_path or exe_name).lower()
                        # Strictly filter out editors, browsers and system processes
                        if not any(ign in p_lower for ign in ("chrome", "msedge", "firefox", "opera", "brave", "code.exe", "devenv", "explorer")):
                            if any(k in p_lower for k in (r"\programs\bobrdobr", r"\program files")):
                                mode = "Установленная версия"
                            else:
                                mode = "Портативная версия"

                            results.append({
                                "pid": pid,
                                "exe_name": pe.szExeFile,
                                "exe_path": exe_path,
                                "mode": mode,
                            })

                if not kernel32.Process32NextW(h_snap, ctypes.byref(pe)):
                    break

        kernel32.CloseHandle(h_snap)
    except Exception:
        pass

    return results


def is_process_alive(pid: int) -> bool:
    """Checks whether a process with given PID is still running."""
    if pid <= 0:
        return False
    if not is_windows():
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return False
        try:
            code = wintypes.DWORD()
            if kernel32.GetExitCodeProcess(h, ctypes.byref(code)):
                STILL_ACTIVE = 259
                return code.value == STILL_ACTIVE
            return False
        finally:
            kernel32.CloseHandle(h)
    except Exception:
        return False


def terminate_bobrdobr_process(pid: int, timeout_sec: float = 3.0) -> bool:
    """
    Safely terminates an existing or hung BobrDobr VPN process.
    1. Sends IPC 'TERMINATE' command (graceful shutdown).
    2. Runs 'taskkill /F /T /PID {pid}' (standard termination).
    3. If access is denied (e.g., standard user terminating an elevated process),
       triggers UAC elevation via Win32 ShellExecuteW('runas', 'taskkill.exe', ...).
    4. Cleans up orphaned Wintun adapters.
    Returns True if process is confirmed dead.
    """
    if not is_process_alive(pid):
        _post_termination_cleanup()
        return True

    # 1. Graceful IPC termination
    try:
        from PySide6.QtNetwork import QLocalSocket
        sock = QLocalSocket()
        sock.connectToServer("BobrDobr_VPN_SingleInstance_IPC")
        if sock.waitForConnected(300):
            sock.write(b"TERMINATE\n")
            sock.waitForBytesWritten(300)
            try:
                sock.disconnectFromServer()
            except Exception:
                pass
            t0 = time.time()
            while time.time() - t0 < 1.2:
                if not is_process_alive(pid):
                    _post_termination_cleanup()
                    return True
                time.sleep(0.1)
    except Exception:
        pass

    if not is_process_alive(pid):
        _post_termination_cleanup()
        return True

    # 2. Standard taskkill
    try:
        import subprocess
        flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
            timeout=2.0,
            creationflags=flags
        )
        t0 = time.time()
        while time.time() - t0 < 1.0:
            if not is_process_alive(pid):
                _post_termination_cleanup()
                return True
            time.sleep(0.1)
    except Exception:
        pass

    if not is_process_alive(pid):
        _post_termination_cleanup()
        return True

    # 3. Escalated UAC termination (standard user terminating elevated process)
    if is_windows():
        try:
            import ctypes
            shell32 = ctypes.windll.shell32
            # 0 = SW_HIDE
            ret = shell32.ShellExecuteW(
                None,
                "runas",
                "taskkill.exe",
                f"/F /T /PID {pid}",
                None,
                0
            )
            # HINSTANCE > 32 indicates ShellExecute succeeded
            if ret > 32:
                t0 = time.time()
                while time.time() - t0 < 3.0:
                    if not is_process_alive(pid):
                        _post_termination_cleanup()
                        return True
                    time.sleep(0.15)
        except Exception:
            pass

    _post_termination_cleanup()
    return not is_process_alive(pid)


def _post_termination_cleanup():
    """Performs immediate cleanup of network adapters and lingering local mutex handles."""
    try:
        from utils.platform_helper import cleanup_orphan_bobrdobr_adapters
        cleanup_orphan_bobrdobr_adapters([], asynchronous=False)
    except Exception:
        pass
    terminate_orphaned_vpn_daemons()
    release_single_instance()


def terminate_all_bobrdobr_processes(processes: List[Dict[str, Any]]) -> bool:
    """Terminates all given processes in list."""
    all_ok = True
    for p in processes:
        pid = p.get("pid")
        if pid and is_process_alive(pid):
            if not terminate_bobrdobr_process(pid):
                all_ok = False
    return all_ok


def terminate_orphaned_vpn_daemons():
    """Terminates any disconnected amneziawg-go or openconnect processes."""
    if not is_windows():
        return
    import subprocess
    flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    for d in ("amneziawg-go.exe", "openconnect.exe"):
        try:
            subprocess.run(["taskkill", "/F", "/IM", d], capture_output=True, timeout=1.5, creationflags=flags)
        except Exception:
            pass


def handle_startup_single_instance(app) -> bool:
    """
    Main entrypoint single instance checker called from main().
    - If no other instance is running, acquires mutex and returns True immediately.
    - If an active instance or ghost process is detected:
      Displays InstanceConflictDialog to let the user choose:
        a) Keep active window -> returns False (exits current process).
        b) Terminate other instance / ghost process -> terminates with UAC if needed,
           re-acquires mutex, and returns True (continues startup!).
    """
    if not is_windows():
        return True

    # 1. Quick initial check - zero latency for single instance
    if try_acquire_single_instance():
        return True

    # 2. Collision detected: inspect processes
    other_procs = find_other_bobrdobr_processes()

    # Attempt to activate existing window
    window_activated = activate_existing_window()
    is_ghost = not window_activated

    # Format process information
    if other_procs:
        proc_info = other_procs[0].copy()
        proc_info["is_responsive"] = window_activated
    else:
        proc_info = {
            "pid": "—",
            "mode": "Фоновый процесс",
            "is_responsive": window_activated
        }

    # 3. Show Interactive Dialog
    app_icon = None
    if app and hasattr(app, "windowIcon"):
        try:
            app_icon = app.windowIcon()
        except Exception:
            app_icon = None

    try:
        from gui.instance_dialog import InstanceConflictDialog
        dlg = InstanceConflictDialog(
            proc_info=proc_info,
            is_ghost=is_ghost,
            app_icon=app_icon
        )
        res = dlg.exec()
    except Exception:
        # Fallback to standard message box if dialog fails
        show_already_running_message()
        return False

    from PySide6.QtWidgets import QDialog
    is_accepted = (res == QDialog.Accepted or res == 1 or getattr(res, "value", None) == 1)
    if is_accepted:
        # User requested to terminate other instance(s) and start here
        if other_procs:
            terminate_all_bobrdobr_processes(other_procs)
        else:
            terminate_orphaned_vpn_daemons()

        time.sleep(0.3)
        # Attempt to acquire mutex again
        if try_acquire_single_instance():
            return True
        time.sleep(0.3)
        if try_acquire_single_instance():
            return True

        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(
            None,
            "БобрДобр VPN",
            "Не удалось завершить предыдущий процесс. Возможно, требуются права Администратора Windows.\n\nЗапуск отменён."
        )
        return False
    else:
        # User chose to keep active window or cancel
        return False
