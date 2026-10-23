import os
import sys
import shutil
import platform
import subprocess
from typing import Optional, List


def is_windows() -> bool:
    """Returns True if running on Windows."""
    return platform.system() == "Windows"


def is_linux() -> bool:
    """Returns True if running on Linux."""
    return platform.system() == "Linux"


def is_admin() -> bool:
    """Checks if the current process has administrator / root privileges."""
    if is_windows():
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False
    else:
        return os.geteuid() == 0


def run_silent_cmd(cmd: List[str], timeout: int = 5) -> subprocess.CompletedProcess:
    """Executes a command silently without flashing a command prompt window on Windows."""
    kwargs = {
        "capture_output": True,
        "text": True,
        "timeout": timeout,
    }
    if is_windows():
        kwargs["creationflags"] = (
            subprocess.CREATE_NO_WINDOW
            if hasattr(subprocess, "CREATE_NO_WINDOW")
            else 0x08000000
        )
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = startupinfo
    return subprocess.run(cmd, **kwargs)



def is_installed_mode() -> bool:
    """
    Returns True if the running binary is inside %LOCALAPPDATA%/Programs/BobrDobr.
    """
    if not getattr(sys, "frozen", False):
        return False
    try:
        local_appdata = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
        inst_dir = os.path.normcase(os.path.abspath(os.path.join(local_appdata, "Programs", "BobrDobr")))
        curr_exe = os.path.normcase(os.path.abspath(sys.executable))
        return curr_exe.startswith(inst_dir)
    except Exception:
        return False


def get_base_dir() -> str:
    """Returns the base directory of the running application, supporting PyInstaller bundles."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def get_persistent_bin_dir() -> str:
    """
    Returns a persistent, fixed directory on the host where binaries live.
    - In installed mode: points directly to %LOCALAPPDATA%/Programs/BobrDobr/bin/windows
      (no redundant duplicate folder created on disk).
    - In portable mode: points to %LOCALAPPDATA%/BobrDobr/bin to prevent Windows Firewall
      re-prompting on every restart due to dynamic temp folders.
    """
    if is_windows():
        local_appdata = os.environ.get("LOCALAPPDATA")
        if not local_appdata:
            local_appdata = os.path.join(os.path.expanduser("~"), "AppData", "Local")

        if is_installed_mode():
            base = os.path.join(local_appdata, "Programs", "BobrDobr", "bin", "windows")
        else:
            base = os.path.join(local_appdata, "BobrDobr", "bin")
    else:
        base = os.path.expanduser("~/.local/share/bobrdobr/bin")

    os.makedirs(base, exist_ok=True)
    return base


def cleanup_stale_mei_folders() -> None:
    """Silently cleans up orphaned _MEIxxxxxx directories in Temp from past crashed or terminated sessions."""
    if not is_windows():
        return
    try:
        import tempfile
        temp_dir = tempfile.gettempdir()
        current_mei = getattr(sys, "_MEIPASS", None)
        for entry in os.listdir(temp_dir):
            if entry.startswith("_MEI") and entry != os.path.basename(current_mei or ""):
                target = os.path.join(temp_dir, entry)
                if os.path.isdir(target):
                    try:
                        shutil.rmtree(target, ignore_errors=True)
                    except Exception:
                        pass
    except Exception:
        pass


def cleanup_stale_temp_configs() -> None:
    """Silently cleans up orphaned awg_*.conf files in Temp from past sessions."""
    if not is_windows():
        return
    try:
        import tempfile
        import glob
        temp_dir = tempfile.gettempdir()
        for conf in glob.glob(os.path.join(temp_dir, "awg_*.conf")):
            try:
                os.remove(conf)
            except Exception:
                pass
    except Exception:
        pass


_GLOBAL_JOB_OBJECT = None


def init_windows_job_object() -> bool:
    """
    Creates a Windows Job Object with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    and binds the current process to it. This guarantees that all child
    processes (amneziawg-go, openconnect) are terminated by Windows kernel
    whenever the main process terminates or crashes.
    """
    global _GLOBAL_JOB_OBJECT
    if not is_windows() or _GLOBAL_JOB_OBJECT is not None:
        return True

    try:
        import ctypes
        from ctypes import wintypes

        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
        JobObjectExtendedLimitInformation = 9

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
                ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_uint64),
                ("WriteOperationCount", ctypes.c_uint64),
                ("OtherOperationCount", ctypes.c_uint64),
                ("ReadTransferCount", ctypes.c_uint64),
                ("WriteTransferCount", ctypes.c_uint64),
                ("OtherTransferCount", ctypes.c_uint64),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryLimit", ctypes.c_size_t),
                ("PeakJobMemoryLimit", ctypes.c_size_t),
            ]

        kernel32 = ctypes.windll.kernel32
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return False

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        ret = kernel32.SetInformationJobObject(
            job,
            JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            ctypes.sizeof(info)
        )
        if ret == 0:
            return False

        current_proc = kernel32.GetCurrentProcess()
        if kernel32.AssignProcessToJobObject(job, current_proc) == 0:
            return False

        _GLOBAL_JOB_OBJECT = job
        return True
    except Exception:
        return False


def is_process_running(process_name: str) -> bool:
    """
    Sub-millisecond native Windows check if a process matching process_name is running.
    Uses CreateToolhelp32Snapshot without spawning child processes.
    """
    if not is_windows() or not process_name:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        TH32CS_SNAPPROCESS = 0x00000002
        kernel32 = ctypes.windll.kernel32

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

        h_snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if h_snap == -1 or h_snap == 0:
            return False

        pe = PROCESSENTRY32W()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        target = process_name.lower().rstrip(".exe")

        running = False
        if kernel32.Process32FirstW(h_snap, ctypes.byref(pe)):
            while True:
                curr_name = pe.szExeFile.lower().rstrip(".exe")
                if curr_name == target:
                    running = True
                    break
                if not kernel32.Process32NextW(h_snap, ctypes.byref(pe)):
                    break
        kernel32.CloseHandle(h_snap)
        return running
    except Exception:
        return False


def is_network_adapter_present(adapter_name: str) -> bool:
    """
    Ultra-fast check (sub-millisecond) if a network adapter with the given name exists in Windows.
    Uses ConvertInterfaceNameToLuidW from iphlpapi.dll with a fast netsh fallback.
    """
    if not is_windows() or not adapter_name:
        return False
    try:
        import ctypes
        iphlpapi = ctypes.windll.iphlpapi
        luid = ctypes.c_uint64()
        res = iphlpapi.ConvertInterfaceNameToLuidW(
            ctypes.c_wchar_p(adapter_name),
            ctypes.byref(luid)
        )
        return res == 0
    except Exception:
        pass

    try:
        res = run_silent_cmd(["netsh", "interface", "show", "interface", f"name={adapter_name}"], timeout=2)
        return res.returncode == 0 and adapter_name.lower() in (res.stdout or "").lower()
    except Exception:
        return False


def kill_amnezia_daemons() -> None:
    """Kills any orphaned AmneziaWG daemon processes only if running."""
    if not is_windows():
        return
    if not is_process_running("amneziawg-go") and not is_process_running("amneziawg"):
        return
    for proc_name in ["amneziawg-go.exe", "amneziawg.exe"]:
        run_silent_cmd(["taskkill", "/F", "/T", "/IM", proc_name], timeout=2)


def kill_openconnect_daemons() -> None:
    """Kills any orphaned OpenConnect daemon processes only if running."""
    if not is_windows():
        return
    if not is_process_running("openconnect"):
        return
    run_silent_cmd(["taskkill", "/F", "/T", "/IM", "openconnect.exe"], timeout=2)


def cleanup_orphaned_vpn_daemons() -> None:
    """Kills all orphaned VPN daemon processes across all supported protocols."""
    kill_amnezia_daemons()
    kill_openconnect_daemons()


def get_wintun_device_instances() -> List[str]:
    """
    Returns a list of PnP device instance IDs for any Wintun / WireGuard devices
    currently registered in the Windows registry (e.g. ['SWD\\WINTUN\\{...}']).
    Runs in memory via winreg in <0.1 ms.
    """
    if not is_windows():
        return []
    import winreg
    instances = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Enum\SWD\WINTUN", 0, winreg.KEY_READ) as key:
            num_subkeys, _, _ = winreg.QueryInfoKey(key)
            for i in range(num_subkeys):
                guid = winreg.EnumKey(key, i)
                instances.append(f"SWD\\WINTUN\\{guid}")
    except (FileNotFoundError, OSError):
        pass
    return instances


def delete_wintun_adapter(interface_name: str = "") -> None:
    """
    Finds and removes stale/phantom Wintun or WireGuard adapters.
    1. Instantly queries SWD\\WINTUN registry instances (<0.1ms).
    2. Removes any detected Wintun devices via direct pnputil /remove-device calls (~20ms each, NO PowerShell!).
    3. If an interface_name is specified and still present in network adapters, cleans it up.
    """
    if not is_windows():
        return

    # Direct fast removal of all SWD\WINTUN devices (takes ~20ms, no PowerShell)
    instances = get_wintun_device_instances()
    for inst_id in instances:
        try:
            run_silent_cmd(["pnputil.exe", "/remove-device", inst_id, "/subtree"], timeout=4)
        except Exception:
            pass

    # Fallback only if the named adapter still exists in network stack
    if interface_name and is_network_adapter_present(interface_name):
        ps_cmd = (
            f"$dev = Get-NetAdapter -Name '{interface_name}' -ErrorAction SilentlyContinue; "
            "if ($dev -and $dev.PnPDeviceID) { pnputil /remove-device $dev.PnPDeviceID | Out-Null }"
        )
        try:
            run_silent_cmd(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
                timeout=5
            )
        except Exception:
            pass


def ensure_persistent_binaries() -> None:
    """
    Extracts bundled binaries (amneziawg-go, wintun.dll, openconnect) to a permanent
    host path and registers firewall authorization so security prompts never re-appear.
    Also cleans up leftover temporary directories and configs.
    In installed mode, eliminates duplicate bin directory if present.
    """
    if not is_windows():
        return

    cleanup_stale_mei_folders()
    cleanup_stale_temp_configs()
    cleanup_orphaned_vpn_daemons()

    # In installed mode, clean up obsolete %LOCALAPPDATA%/BobrDobr duplicate folder if it exists
    if is_installed_mode():
        try:
            local_appdata = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
            legacy_dir = os.path.join(local_appdata, "BobrDobr")
            if os.path.isdir(legacy_dir):
                shutil.rmtree(legacy_dir, ignore_errors=True)
        except Exception:
            pass

    try:
        persistent_dir = get_persistent_bin_dir()
        base_dir = get_base_dir()
        bundled_dir = os.path.join(base_dir, "bin", "windows")

        # Only copy if persistent_dir is different from bundled_dir (i.e. portable mode)
        if os.path.normcase(os.path.abspath(persistent_dir)) != os.path.normcase(os.path.abspath(bundled_dir)):
            if os.path.isdir(bundled_dir):
                for fname in os.listdir(bundled_dir):
                    src_file = os.path.join(bundled_dir, fname)
                    dst_file = os.path.join(persistent_dir, fname)
                    if os.path.isfile(src_file):
                        # Copy if destination doesn't exist or size differs
                        if not os.path.exists(dst_file) or os.path.getsize(src_file) != os.path.getsize(dst_file):
                            try:
                                shutil.copy2(src_file, dst_file)
                            except Exception:
                                pass

        # If running as Administrator, auto-authorize amneziawg-go in Windows Firewall
        awg_bin = os.path.join(persistent_dir, "amneziawg-go.exe")
        if os.path.isfile(awg_bin) and is_admin():
            _register_firewall_rule(awg_bin)

    except Exception as e:
        print(f"Error initializing persistent binaries: {e}")


def _register_firewall_rule(program_path: str) -> None:
    """Silently registers an inbound firewall allowance for the persistent binary."""
    rule_name = "BobrDobr-AmneziaWG"
    try:
        # Check if rule exists
        check_cmd = ["netsh", "advfirewall", "firewall", "show", "rule", f"name={rule_name}"]
        res = run_silent_cmd(check_cmd, timeout=3)
        if res.returncode != 0 or program_path.lower() not in res.stdout.lower():
            # Delete old/outdated rule if exists
            run_silent_cmd(["netsh", "advfirewall", "firewall", "delete", "rule", f"name={rule_name}"], timeout=3)
            # Add fresh rule
            add_cmd = [
                "netsh", "advfirewall", "firewall", "add", "rule",
                f"name={rule_name}",
                "dir=in",
                "action=allow",
                f"program={program_path}",
                "enable=yes",
                "profile=any"
            ]
            run_silent_cmd(add_cmd, timeout=4)
    except Exception:
        pass


def remove_firewall_rule() -> None:
    """Silently removes the firewall rule for BobrDobr-AmneziaWG on uninstall."""
    if not is_windows():
        return
    try:
        run_silent_cmd(["netsh", "advfirewall", "firewall", "delete", "rule", "name=BobrDobr-AmneziaWG"], timeout=3)
    except Exception:
        pass


def find_binary(binary_name: str) -> Optional[str]:
    """
    Locates an executable binary by checking:
    1. Persistent host directory (%LOCALAPPDATA%/BobrDobr/bin)
    2. PyInstaller bundled path or application root bin/<platform>/ directory
    3. Relative bin/<platform>/ directory from current working directory
    4. System PATH
    """
    os_folder = "windows" if is_windows() else "linux"
    ext = ".exe" if is_windows() and not binary_name.endswith(".exe") else ""
    full_name = f"{binary_name}{ext}"

    # 1. Prefer persistent host directory
    persistent_cand = os.path.join(get_persistent_bin_dir(), full_name)
    if os.path.isfile(persistent_cand):
        return os.path.abspath(persistent_cand)

    base_dir = get_base_dir()
    candidates: List[str] = [
        # Inside bundled resources
        os.path.join(base_dir, "bin", os_folder, full_name),
        os.path.join(base_dir, "bin", full_name),
        os.path.join(base_dir, full_name),
        # Relative to cwd
        os.path.join(os.getcwd(), "bin", os_folder, full_name),
        os.path.join(os.getcwd(), "bin", full_name),
    ]

    for candidate in candidates:
        if os.path.isfile(candidate) and (is_windows() or os.access(candidate, os.X_OK)):
            return os.path.abspath(candidate)

    # Fall back to system PATH
    system_path = shutil.which(binary_name)
    if system_path:
        return system_path

    if is_windows():
        system_path = shutil.which(full_name)
        if system_path:
            return system_path

    return None


def get_wintun_path() -> Optional[str]:
    """Finds wintun.dll on Windows, checking persistent host directory first."""
    if not is_windows():
        return None

    persistent_cand = os.path.join(get_persistent_bin_dir(), "wintun.dll")
    if os.path.isfile(persistent_cand):
        return os.path.abspath(persistent_cand)

    base_dir = get_base_dir()
    candidates = [
        os.path.join(base_dir, "bin", "windows", "wintun.dll"),
        os.path.join(base_dir, "wintun.dll"),
        os.path.join(os.getcwd(), "bin", "windows", "wintun.dll"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return os.path.abspath(c)
    return None
