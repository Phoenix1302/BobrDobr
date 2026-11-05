import os
import sys
import shutil
import platform
import subprocess
from typing import Optional, List, Tuple, Dict, Any


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


def get_bobrdobr_daemon_pids(names: Optional[List[str]] = None) -> List[int]:
    """
    Returns PIDs of running daemon processes that belong exclusively to this BobrDobr application.
    Checks process parent PID and binary image path against BobrDobr's persistent directories
    to prevent terminating unrelated VPN software or system daemons.
    """
    if not is_windows():
        return []
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.windll.kernel32

    if names is None:
        target_names = {"amneziawg-go.exe", "amneziawg.exe", "wireguard.exe", "openconnect.exe"}
    else:
        target_names = {n.lower().rstrip(".exe") + ".exe" for n in names}

    TH32CS_SNAPPROCESS = 0x00000002

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ('dwSize', wintypes.DWORD),
            ('cntUsage', wintypes.DWORD),
            ('th32ProcessID', wintypes.DWORD),
            ('th32DefaultHeapID', ctypes.POINTER(wintypes.ULONG)),
            ('th32ModuleID', wintypes.DWORD),
            ('cntThreads', wintypes.DWORD),
            ('th32ParentProcessID', wintypes.DWORD),
            ('pcPriClassBase', wintypes.LONG),
            ('dwFlags', wintypes.DWORD),
            ('szExeFile', wintypes.WCHAR * 260)
        ]

    h_snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if h_snap == -1 or h_snap == 0:
        return []

    curr_pid = os.getpid()
    trusted_dirs = []
    try:
        trusted_dirs.append(os.path.normcase(os.path.abspath(get_persistent_bin_dir())))
    except Exception:
        pass
    try:
        from utils.installer_helper import get_install_dir
        trusted_dirs.append(os.path.normcase(os.path.abspath(get_install_dir())))
    except Exception:
        pass
    try:
        trusted_dirs.append(os.path.normcase(os.path.abspath(get_base_dir())))
    except Exception:
        pass
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        try:
            trusted_dirs.append(os.path.normcase(os.path.abspath(meipass)))
        except Exception:
            pass

    pe = PROCESSENTRY32W()
    pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    matched_pids = []

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    if kernel32.Process32FirstW(h_snap, ctypes.byref(pe)):
        while True:
            proc_name = pe.szExeFile.lower()
            if proc_name in target_names:
                pid = pe.th32ProcessID
                parent_pid = pe.th32ParentProcessID

                # If current process is the parent, it definitely belongs to us
                if parent_pid == curr_pid:
                    matched_pids.append(pid)
                else:
                    # Otherwise inspect process executable image path
                    h_proc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
                    if h_proc:
                        try:
                            buf = ctypes.create_unicode_buffer(1024)
                            sz = wintypes.DWORD(1024)
                            if kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(sz)):
                                img_path = os.path.normcase(os.path.abspath(buf.value))
                                is_ours = False
                                for t_dir in trusted_dirs:
                                    if img_path.startswith(t_dir):
                                        is_ours = True
                                        break
                                if not is_ours and "bobrdobr" in img_path:
                                    is_ours = True
                                if is_ours:
                                    matched_pids.append(pid)
                        finally:
                            kernel32.CloseHandle(h_proc)

            if not kernel32.Process32NextW(h_snap, ctypes.byref(pe)):
                break

    kernel32.CloseHandle(h_snap)
    return matched_pids


def kill_bobrdobr_daemons(pids: List[int]) -> None:
    """Terminates specific daemon processes belonging exclusively to BobrDobr."""
    if not is_windows() or not pids:
        return
    import ctypes
    kernel32 = ctypes.windll.kernel32
    PROCESS_TERMINATE = 0x0001
    for pid in pids:
        try:
            h = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
            if h:
                kernel32.TerminateProcess(h, 1)
                kernel32.CloseHandle(h)
            else:
                run_silent_cmd(["taskkill", "/F", "/PID", str(pid)], timeout=2)
        except Exception:
            pass


def kill_amnezia_daemons(only_this_app: bool = True) -> None:
    """Kills orphaned AmneziaWG daemon processes. If only_this_app is True, targets only BobrDobr's own processes."""
    if not is_windows():
        return
    if only_this_app:
        pids = get_bobrdobr_daemon_pids(["amneziawg-go.exe", "amneziawg.exe", "wireguard.exe"])
        kill_bobrdobr_daemons(pids)
    else:
        if not is_process_running("amneziawg-go") and not is_process_running("amneziawg"):
            return
        for proc_name in ["amneziawg-go.exe", "amneziawg.exe"]:
            run_silent_cmd(["taskkill", "/F", "/T", "/IM", proc_name], timeout=2)


def kill_openconnect_daemons(only_this_app: bool = True) -> None:
    """Kills orphaned OpenConnect daemon processes. If only_this_app is True, targets only BobrDobr's own processes."""
    if not is_windows():
        return
    if only_this_app:
        pids = get_bobrdobr_daemon_pids(["openconnect.exe"])
        kill_bobrdobr_daemons(pids)
    else:
        if not is_process_running("openconnect"):
            return
        run_silent_cmd(["taskkill", "/F", "/T", "/IM", "openconnect.exe"], timeout=2)


def cleanup_orphaned_vpn_daemons(only_this_app: bool = True) -> None:
    """Kills all orphaned VPN daemon processes across all supported protocols."""
    kill_amnezia_daemons(only_this_app=only_this_app)
    kill_openconnect_daemons(only_this_app=only_this_app)


_LAST_ASSIGNED_ADAPTER: Optional[str] = None


def reset_adapter_rotation() -> None:
    """Resets the adapter rotation tracker (used in unit tests and re-initialization)."""
    global _LAST_ASSIGNED_ADAPTER
    _LAST_ASSIGNED_ADAPTER = None


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


def get_wintun_interface_for_instance(instance_id: str) -> Optional[str]:
    """
    Resolves the network interface name (e.g. 'awg0') for a given SWD\\WINTUN\\{GUID} device instance.
    Checks Network Connection name in registry, then FriendlyName / DeviceDesc.
    """
    if not is_windows() or not instance_id:
        return None
    import winreg
    guid = instance_id.split("\\")[-1]

    # 1. Check Network connection name
    net_path = rf"SYSTEM\CurrentControlSet\Control\Network\{{4d36e972-e325-11ce-bfc1-08002be10318}}\{guid}\Connection"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, net_path, 0, winreg.KEY_READ) as k:
            name, _ = winreg.QueryValueEx(k, "Name")
            if name:
                return str(name).strip()
    except (FileNotFoundError, OSError):
        pass

    # 2. Check FriendlyName or DeviceDesc under Enum\SWD\WINTUN\{guid}
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, rf"SYSTEM\CurrentControlSet\Enum\SWD\WINTUN\{guid}", 0, winreg.KEY_READ) as k:
            for prop in ["FriendlyName", "DeviceDesc"]:
                try:
                    val, _ = winreg.QueryValueEx(k, prop)
                    if val:
                        s_val = str(val).strip()
                        if s_val.lower() not in ("wireguard tunnel", "wintun userspace tunnel"):
                            return s_val
                except (FileNotFoundError, OSError):
                    pass
    except (FileNotFoundError, OSError):
        pass

    return None


def is_tunnel_adapter_busy(adapter_name: str) -> bool:
    """
    Checks if a network adapter is currently active, occupied, or in the process
    of PnP teardown in Windows.
    Verifies both the network interface stack and SWD\\WINTUN registry instances.
    """
    if not is_windows() or not adapter_name:
        return False

    target = adapter_name.strip().lower()

    # 1. Fast network stack presence check
    if is_network_adapter_present(target):
        return True

    # 2. Check registered Wintun devices via get_wintun_device_instances()
    try:
        for inst_id in get_wintun_device_instances():
            iface_name = get_wintun_interface_for_instance(inst_id)
            if iface_name and iface_name.lower() == target:
                return True
    except Exception:
        pass

    return False


def get_next_available_tunnel_adapter(preferred: str = "bobr0") -> str:
    """
    Selects the next clean, available tunnel adapter for AmneziaWG/WireGuard:
    1. Checks not only is_network_adapter_present, but also the SWD\\WINTUN registry
       via get_wintun_device_instances().
    2. Dedicated BobrDobr naming with ping-pong rotation ('bobr0' <-> 'bobr1')
       on rapid reconnects or hot-switches to avoid waiting for Windows PnP teardown of the old device.
    3. If preferred is busy or in teardown, dynamically finds the next free adapter (bobr1, bobr0, bobr2, ...).
    """
    global _LAST_ASSIGNED_ADAPTER

    if not is_windows():
        return preferred or "bobr0"

    target_pref = (preferred or "bobr0").strip()
    prefix = "".join(c for c in target_pref if not c.isdigit()) or "bobr"

    # Determine candidate order with ping-pong rotation:
    # If _LAST_ASSIGNED_ADAPTER was bobr0, rotate to bobr1 first, then bobr0, bobr2, etc.
    # If _LAST_ASSIGNED_ADAPTER was bobr1, rotate to bobr0 first, then bobr1, bobr2, etc.
    candidates = []
    if _LAST_ASSIGNED_ADAPTER and _LAST_ASSIGNED_ADAPTER.startswith(prefix):
        try:
            last_idx = int("".join(c for c in _LAST_ASSIGNED_ADAPTER if c.isdigit()))
        except ValueError:
            last_idx = 0

        # Alternate between 0 and 1 primarily for smooth two-adapter ping-pong (bobr0 <-> bobr1)
        if last_idx == 0:
            preferred_order = [1, 0] + [i for i in range(2, 10)]
        elif last_idx == 1:
            preferred_order = [0, 1] + [i for i in range(2, 10)]
        else:
            preferred_order = [0, 1] + [i for i in range(2, 10) if i != last_idx]
            preferred_order.append(last_idx)

        for idx in preferred_order:
            candidates.append(f"{prefix}{idx}")
    else:
        # First call: target_pref first, then alternate
        try:
            pref_idx = int("".join(c for c in target_pref if c.isdigit()))
        except ValueError:
            pref_idx = 0

        if pref_idx == 0:
            order = [0, 1] + [i for i in range(2, 10)]
        elif pref_idx == 1:
            order = [1, 0] + [i for i in range(2, 10)]
        else:
            order = [pref_idx, 0, 1] + [i for i in range(2, 10) if i != pref_idx]

        for idx in order:
            candidates.append(f"{prefix}{idx}")

    # Remove duplicates preserving order
    seen = set()
    ordered_candidates = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            ordered_candidates.append(c)

    # Scan for first non-busy adapter
    for cand in ordered_candidates:
        if not is_tunnel_adapter_busy(cand):
            _LAST_ASSIGNED_ADAPTER = cand
            return cand

    # Fallback if all 0..9 are busy
    fallback = ordered_candidates[0]
    _LAST_ASSIGNED_ADAPTER = fallback
    return fallback


def prepare_tunnel_adapter(interface_name: str = "bobr0") -> Tuple[bool, str]:
    """
    Pre-connection safety gate for Wintun / WireGuard network adapters:
    1. Terminates any lingering/orphaned daemon processes belonging to this application.
    2. Checks if the requested adapter is present and busy.
    3. If present and lingering without active processes, cleans up phantom adapter device.
    4. If the adapter is occupied, finds an available fallback (bobr1, bobr0, bobr2, etc.)
       using non-blocking checks without artificial sleeps.
    Returns (success, ready_interface_name).
    """
    if not is_windows():
        return True, interface_name

    target_iface = (interface_name or "").strip() or "bobr0"

    # 1. Clean up any orphaned BobrDobr daemon processes
    pids = get_bobrdobr_daemon_pids(["amneziawg-go.exe", "amneziawg.exe", "wireguard.exe"])
    if pids:
        kill_bobrdobr_daemons(pids)

    # 2. Check if the target adapter is free
    if not is_network_adapter_present(target_iface) and not is_tunnel_adapter_busy(target_iface):
        return True, target_iface

    # 3. Adapter exists: attempt fast removal of stale/phantom device
    delete_wintun_adapter(target_iface)
    if not is_network_adapter_present(target_iface) and not is_tunnel_adapter_busy(target_iface):
        return True, target_iface

    # 4. If target_iface is STILL present or busy, automatically select a free alternative
    # without blocking the launch.
    alt_iface = get_next_available_tunnel_adapter(target_iface)
    if alt_iface and alt_iface != target_iface and not is_tunnel_adapter_busy(alt_iface):
        return True, alt_iface

    prefix = "".join(c for c in target_iface if not c.isdigit()) or "bobr"
    for idx in range(1, 10):
        cand = f"{prefix}{idx}"
        if not is_network_adapter_present(cand) and not is_tunnel_adapter_busy(cand):
            return True, cand

    return False, target_iface


def cleanup_orphan_bobrdobr_adapters(
    active_interfaces: Optional[Any] = None,
    asynchronous: bool = True
) -> None:
    """
    Scans SWD\\WINTUN device nodes and network interfaces exclusively for adapters
    named 'bobr*' (and legacy 'awg*') that do not belong to the currently running session,
    and cleans them up safely.

    Never touches third-party adapters (Wi-Fi, Ethernet, Tailscale, ZeroTier, etc.).
    If asynchronous=True, runs in a detached daemon thread without blocking the caller.
    """
    if not is_windows():
        return

    # Normalize active interfaces set
    active_set = set()
    if active_interfaces:
        for iface in active_interfaces:
            if iface:
                active_set.add(str(iface).strip().lower())

    def _cleanup_worker():
        try:
            # 1. Scan SWD\WINTUN registry device instances
            wintun_instances = get_wintun_device_instances()
            for inst_id in wintun_instances:
                try:
                    iface_name = get_wintun_interface_for_instance(inst_id)
                    should_remove = False

                    if iface_name:
                        lower_name = iface_name.strip().lower()
                        # Strictly target only bobr* and legacy awg*
                        if (lower_name.startswith("bobr") or lower_name.startswith("awg")) and lower_name not in active_set:
                            should_remove = True
                    else:
                        # If interface name is unmapped in Connection\Name, check FriendlyName / DeviceDesc in registry
                        import winreg
                        guid = inst_id.split("\\")[-1]
                        try:
                            with winreg.OpenKey(
                                winreg.HKEY_LOCAL_MACHINE,
                                rf"SYSTEM\CurrentControlSet\Enum\SWD\WINTUN\{guid}",
                                0,
                                winreg.KEY_READ
                            ) as k:
                                for prop in ["FriendlyName", "DeviceDesc"]:
                                    try:
                                        val, _ = winreg.QueryValueEx(k, prop)
                                        s_val = str(val).strip().lower()
                                        if (s_val.startswith("bobr") or s_val.startswith("awg")) and s_val not in active_set:
                                            should_remove = True
                                            break
                                    except (FileNotFoundError, OSError):
                                        pass
                        except (FileNotFoundError, OSError):
                            pass

                    if should_remove:
                        run_silent_cmd(["pnputil.exe", "/remove-device", inst_id, "/subtree"], timeout=4)
                except Exception:
                    pass

            # 2. Scan network interfaces for orphaned 'bobr*' or legacy 'awg*' adapters
            try:
                res = run_silent_cmd(["netsh", "interface", "show", "interface"], timeout=3)
                if res.returncode == 0 and res.stdout:
                    for line in res.stdout.splitlines():
                        parts = line.strip().split()
                        if len(parts) >= 4:
                            candidate_name = parts[-1].strip()
                            cand_lower = candidate_name.lower()
                            if (cand_lower.startswith("bobr") or cand_lower.startswith("awg")) and cand_lower not in active_set:
                                delete_wintun_adapter(candidate_name)
            except Exception:
                pass

            # 3. Fallback PowerShell check to clean any remaining orphan bobr*/awg* NetAdapters
            filter_check = ""
            if active_set:
                items_str = ", ".join(f"'{x}'" for x in sorted(active_set))
                filter_check = f"if (@({items_str}) -contains $a.Name.ToLower()) {{ continue }}; "

            ps_script = (
                f"$adapters = Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object {{ ($_.Name -like 'bobr*' -or $_.Name -like 'awg*') }}; "
                f"foreach ($a in $adapters) {{ {filter_check}if ($a.PnPDeviceID) {{ pnputil.exe /remove-device $a.PnPDeviceID /subtree | Out-Null }} }}"
            )
            try:
                run_silent_cmd(
                    ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                    timeout=5
                )
            except Exception:
                pass

        except Exception:
            pass

    if asynchronous:
        import threading
        t = threading.Thread(target=_cleanup_worker, name="BobrDobr-Adapter-Cleanup", daemon=True)
        t.start()
    else:
        _cleanup_worker()


def delete_wintun_adapter(interface_name: str = "") -> None:
    """
    Finds and removes stale/phantom Wintun or WireGuard adapters.
    1. If interface_name is provided, removes only the Wintun device matching that interface.
    2. If interface_name is empty, cleans all detected Wintun devices.
    3. If the interface still exists in the network stack, runs PowerShell netadapter removal as fallback.
    """
    if not is_windows():
        return

    instances = get_wintun_device_instances()
    target_name = (interface_name or "").strip().lower()

    for inst_id in instances:
        try:
            # If a specific interface was requested, verify this instance matches it
            if target_name:
                inst_iface = get_wintun_interface_for_instance(inst_id)
                if inst_iface and inst_iface.lower() != target_name:
                    continue
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
    cleanup_orphan_bobrdobr_adapters(asynchronous=True)

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
