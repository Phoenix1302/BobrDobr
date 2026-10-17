import os
import sys
import shutil
import subprocess
import datetime
import uuid
import json
from typing import Optional, Tuple, Dict, Any, List
from utils.platform_helper import is_windows, run_silent_cmd, remove_firewall_rule


def get_install_dir() -> str:
    """Returns the standard per-user installation directory for BobrDobr."""
    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        local_appdata = os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(local_appdata, "Programs", "BobrDobr")


def get_installed_exe_path() -> str:
    """Returns the full path to the installed BobrDobr-VPN.exe binary."""
    return os.path.join(get_install_dir(), "BobrDobr-VPN.exe")


def is_installed_mode() -> bool:
    """
    Returns True if the currently running executable is inside the system
    installation directory (%LOCALAPPDATA%/Programs/BobrDobr).
    """
    if not getattr(sys, "frozen", False):
        return False
    try:
        curr = os.path.normcase(os.path.abspath(sys.executable))
        inst = os.path.normcase(os.path.abspath(get_installed_exe_path()))
        return curr == inst
    except Exception:
        return False


def has_installed_version() -> bool:
    """Returns True if BobrDobr-VPN.exe is already installed on the system."""
    try:
        return os.path.isfile(get_installed_exe_path())
    except Exception:
        return False


def get_desktop_shortcut_path() -> str:
    """Returns path to the Desktop shortcut."""
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    return os.path.join(desktop, "БобрДобр VPN.lnk")


def get_start_menu_shortcut_path() -> str:
    """Returns path to the Start Menu Programs shortcut."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        appdata = os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
    programs = os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs")
    return os.path.join(programs, "БобрДобр VPN.lnk")


def create_windows_shortcut(target_exe: str, lnk_path: str, description: str = "БобрДобр VPN", run_as_admin: bool = False) -> bool:
    """Creates a Windows .lnk shortcut via WScript.Shell without showing console window."""
    if not is_windows():
        return False
    try:
        target_dir = os.path.dirname(os.path.abspath(target_exe))
        os.makedirs(os.path.dirname(os.path.abspath(lnk_path)), exist_ok=True)

        clean_target = os.path.abspath(target_exe).replace("'", "''")
        clean_lnk = os.path.abspath(lnk_path).replace("'", "''")
        clean_dir = target_dir.replace("'", "''")

        ps_code = (
            f"$ws = New-Object -ComObject WScript.Shell; "
            f"$s = $ws.CreateShortcut('{clean_lnk}'); "
            f"$s.TargetPath = '{clean_target}'; "
            f"$s.WorkingDirectory = '{clean_dir}'; "
            f"$s.IconLocation = '{clean_target},0'; "
            f"$s.Description = '{description}'; "
            f"$s.Save()"
        )
        run_silent_cmd(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_code], timeout=6)

        # Set SLDF_RUNAS_USER flag in .lnk header if run_as_admin requested
        if run_as_admin and os.path.isfile(lnk_path):
            try:
                with open(lnk_path, "r+b") as f:
                    f.seek(0x15)
                    b = f.read(1)
                    if b:
                        f.seek(0x15)
                        f.write(bytes([ord(b) | 0x20]))
            except Exception:
                pass

        return os.path.isfile(lnk_path)
    except Exception as e:
        print(f"Error creating shortcut: {e}")
        return False


def kill_other_bobr_processes() -> None:
    """Terminates other running BobrDobr-VPN.exe processes to avoid file lock during update."""
    if not is_windows():
        return
    try:
        curr_pid = os.getpid()
        ps_cmd = (
            f"Get-Process -Name 'BobrDobr-VPN' -ErrorAction SilentlyContinue | "
            f"Where-Object {{ $_.Id -ne {curr_pid} }} | "
            f"Stop-Process -Force -ErrorAction SilentlyContinue"
        )
        run_silent_cmd(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd], timeout=5)
    except Exception:
        pass


def safe_replace_installed_exe(current_exe: str, installed_exe: str) -> None:
    """
    Safely copies current_exe to installed_exe.
    Handles file-lock issues on Windows by terminating other instances
    and using atomic rename fallback.
    """
    if os.path.normcase(current_exe) == os.path.normcase(installed_exe):
        return

    kill_other_bobr_processes()
    os.makedirs(os.path.dirname(installed_exe), exist_ok=True)

    if os.path.isfile(installed_exe):
        try:
            shutil.copy2(current_exe, installed_exe)
            return
        except (PermissionError, OSError):
            pass

        # Windows file replacement trick: rename the locked file, then copy fresh file
        old_exe = installed_exe + f".old_{uuid.uuid4().hex[:6]}"
        try:
            os.rename(installed_exe, old_exe)
            shutil.copy2(current_exe, installed_exe)
            try:
                os.remove(old_exe)
            except Exception:
                schedule_self_delete(old_exe)
            return
        except Exception as e:
            raise RuntimeError(f"Не удалось обновить исполняемый файл: {e}")

    shutil.copy2(current_exe, installed_exe)


def clean_persistent_binary_cache() -> None:
    """Removes cached binaries in %LOCALAPPDATA%/BobrDobr/bin/ to force fresh extraction on next run."""
    try:
        local_appdata = os.environ.get("LOCALAPPDATA")
        if not local_appdata:
            local_appdata = os.path.join(os.path.expanduser("~"), "AppData", "Local")
        bin_dir = os.path.join(local_appdata, "BobrDobr", "bin")
        if os.path.isdir(bin_dir):
            shutil.rmtree(bin_dir, ignore_errors=True)
    except Exception:
        pass


def sanitize_profile(p: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Sanitizes a single connection profile to canonical clean format,
    discarding all version-specific or stale parameters, and keeping only
    pure connection configuration.
    """
    if not isinstance(p, dict):
        return None

    proto = p.get("proto")
    name = str(p.get("name") or "").strip()
    p_id = str(p.get("id") or uuid.uuid4())

    # Detect protocol if missing
    if not proto:
        if p.get("server") or p.get("camouflage") or "openconnect" in name.lower():
            proto = "openconnect"
        else:
            proto = "amnezia"

    if proto == "openconnect":
        server = str(p.get("server") or "").strip()
        if not server:
            return None

        try:
            port = int(p.get("port", 443))
            if port < 1 or port > 65535:
                port = 443
        except (ValueError, TypeError):
            port = 443

        username = str(p.get("username") or "").strip()
        password = str(p.get("password") or "")
        camouflage = str(p.get("camouflage") or "").strip()
        remember_pwd = bool(p.get("remember_password", True))

        if not name:
            name = username or server or "OpenConnect VPN"

        clean = {
            "id": p_id,
            "name": name,
            "proto": "openconnect",
            "protocol": "anyconnect",
            "server": server,
            "port": port,
            "camouflage": camouflage,
            "username": username,
            "password": password,
            "remember_password": remember_pwd,
        }
        return clean

    elif proto == "amnezia":
        from core.amnezia import AmneziaWGLauncher

        content = str(p.get("config_content") or "").strip()
        cfg_path = str(p.get("config_path") or "").strip()

        if not content and cfg_path and os.path.isfile(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read().strip()
            except Exception:
                pass

        if not content:
            return None

        endpoint = str(p.get("endpoint") or "")
        address = str(p.get("address") or "")
        dns = str(p.get("dns") or "")
        allowed_ips = str(p.get("allowed_ips") or "")
        obfuscation = p.get("obfuscation") if isinstance(p.get("obfuscation"), dict) else {}

        try:
            parsed = AmneziaWGLauncher.parse_config_text(content)
            if parsed.get("endpoint"):
                endpoint = parsed["endpoint"]
            if parsed.get("address"):
                address = parsed["address"]
            if parsed.get("dns"):
                dns = parsed["dns"]
            if parsed.get("allowed_ips"):
                allowed_ips = parsed["allowed_ips"]
            if parsed.get("obfuscation"):
                obfuscation = parsed["obfuscation"]
        except Exception:
            pass

        if not name:
            name = f"AmneziaWG ({endpoint})" if endpoint else "AmneziaWG VPN"

        clean = {
            "id": p_id,
            "name": name,
            "proto": "amnezia",
            "interface": str(p.get("interface") or "awg0").strip() or "awg0",
            "config_content": content,
            "config_path": cfg_path if (cfg_path and os.path.isfile(cfg_path)) else "",
            "endpoint": endpoint,
            "address": address,
            "dns": dns,
            "allowed_ips": allowed_ips,
            "obfuscation": obfuscation,
        }
        return clean

    return None


def perform_clean_settings_migration() -> int:
    """
    Performs a clean-slate settings upgrade for the installed system version:
    1. Reads profiles from active settings (portable or existing installed).
    2. Backs up existing installed settings.json if present.
    3. Sanitizes all profiles to canonical schema.
    4. Resets all other launcher settings to pure baseline defaults.
    5. Saves clean settings.json for the installed system version.
    Returns the count of successfully migrated profiles.
    """
    from utils.config_store import get_config_dir, get_installed_config_path, settings
    from utils.version import APP_VERSION

    installed_config_path = get_installed_config_path()
    raw_profiles = list(settings.get_profiles())

    if os.path.isfile(installed_config_path):
        try:
            backup_dir = os.path.join(get_config_dir(), "backups")
            os.makedirs(backup_dir, exist_ok=True)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(backup_dir, f"settings_pre_upgrade_{ts}.json")
            shutil.copy2(installed_config_path, backup_path)
        except Exception as e:
            print(f"Warning: could not create settings backup: {e}")

        # Also pull any profiles from existing installed settings.json if upgrading
        try:
            with open(installed_config_path, "r", encoding="utf-8") as f:
                inst_data = json.load(f)
            if isinstance(inst_data, dict) and isinstance(inst_data.get("profiles"), list):
                raw_profiles.extend(inst_data["profiles"])
        except Exception:
            pass

    sanitized_profiles = []
    seen_ids = set()
    for p in raw_profiles:
        clean = sanitize_profile(p)
        if clean and clean["id"] not in seen_ids:
            seen_ids.add(clean["id"])
            sanitized_profiles.append(clean)

    # Standard clean baseline configuration
    clean_data = {
        "version": APP_VERSION,
        "profiles": sanitized_profiles,
        "active_profile_id": None,
        "auto_connect": False,
        "minimize_to_tray": True,
        "start_with_windows": False,
    }

    # Write directly to installed_config_path
    os.makedirs(os.path.dirname(installed_config_path), exist_ok=True)
    with open(installed_config_path, "w", encoding="utf-8") as f:
        json.dump(clean_data, f, indent=2, ensure_ascii=False)

    if is_installed_mode():
        settings.data = clean_data
        settings.save()

    return len(sanitized_profiles)


def install_to_system() -> Tuple[bool, str]:
    """
    Copies current executable into %LOCALAPPDATA%/Programs/BobrDobr/
    and creates shortcuts on Desktop and in Start Menu with Administrator privileges.
    """
    if not is_windows():
        return False, "Установка поддерживается только в Windows."
    if not getattr(sys, "frozen", False):
        return False, "Установка доступна при запуске скомпилированного BobrDobr-VPN.exe."

    try:
        current_exe = os.path.abspath(sys.executable)
        install_dir = get_install_dir()
        os.makedirs(install_dir, exist_ok=True)
        installed_exe = get_installed_exe_path()

        # Perform clean migration of settings
        perform_clean_settings_migration()

        # Clean old binary cache
        clean_persistent_binary_cache()

        safe_replace_installed_exe(current_exe, installed_exe)

        desktop_lnk = get_desktop_shortcut_path()
        start_lnk = get_start_menu_shortcut_path()
        create_windows_shortcut(installed_exe, desktop_lnk, run_as_admin=True)
        create_windows_shortcut(installed_exe, start_lnk, run_as_admin=True)

        return True, installed_exe
    except Exception as e:
        return False, str(e)


def update_system_installation() -> Tuple[bool, str, int]:
    """
    Performs clean update of the system installation:
    1. Backs up and sanitizes all existing connection profiles.
    2. Resets all other launcher settings to standard baseline defaults.
    3. Cleans obsolete binary caches.
    4. Safely replaces the installed executable with the currently running binary.
    5. Refreshes Desktop and Start Menu shortcuts.
    Returns (success, message_or_path, migrated_profile_count).
    """
    if not is_windows():
        return False, "Обновление поддерживается только в Windows.", 0
    if not getattr(sys, "frozen", False):
        return False, "Обновление доступно при запуске скомпилированного BobrDobr-VPN.exe.", 0

    try:
        current_exe = os.path.abspath(sys.executable)
        installed_exe = get_installed_exe_path()

        # 1. Clean settings migration
        migrated_count = perform_clean_settings_migration()

        # 2. Clean binary cache
        clean_persistent_binary_cache()

        # 3. Replace installed executable
        safe_replace_installed_exe(current_exe, installed_exe)

        # 4. Refresh shortcuts
        desktop_lnk = get_desktop_shortcut_path()
        start_lnk = get_start_menu_shortcut_path()
        create_windows_shortcut(installed_exe, desktop_lnk, run_as_admin=True)
        create_windows_shortcut(installed_exe, start_lnk, run_as_admin=True)

        return True, installed_exe, migrated_count
    except Exception as e:
        return False, str(e), 0


def kill_installed_processes() -> None:
    """Terminates any background processes running from %LOCALAPPDATA%/Programs/BobrDobr."""
    if not is_windows():
        return
    try:
        inst_exe = os.path.normcase(os.path.abspath(get_installed_exe_path()))
        curr_pid = os.getpid()
        ps_cmd = (
            f"$target = '{inst_exe}'.ToLower(); "
            f"Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | "
            f"Where-Object {{ $_.ExecutablePath -and ($_.ExecutablePath.ToLower() -eq $target) -and ($_.ProcessId -ne {curr_pid}) }} | "
            f"ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}"
        )
        kwargs = {"capture_output": True, "timeout": 5}
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd], **kwargs)
    except Exception:
        pass


def revert_to_portable(target_dir: Optional[str] = None) -> Tuple[bool, str]:
    """
    Copies executable back to Downloads folder, removes shortcuts,
    and schedules removal of the installed system folder.
    """
    if not is_windows():
        return False, "Поддерживается только в Windows."

    try:
        current_exe = os.path.abspath(sys.executable)
        if not target_dir:
            target_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        os.makedirs(target_dir, exist_ok=True)

        portable_exe = os.path.join(target_dir, "BobrDobr-VPN.exe")
        if os.path.normcase(current_exe) != os.path.normcase(portable_exe):
            shutil.copy2(current_exe, portable_exe)

        # Remove shortcuts
        for lnk in [get_desktop_shortcut_path(), get_start_menu_shortcut_path()]:
            if os.path.isfile(lnk):
                try:
                    os.remove(lnk)
                except Exception:
                    pass

        # Copy current installed settings to settings_portable.json so user retains all profiles in portable mode
        try:
            from utils.config_store import get_installed_config_path, get_portable_config_path
            inst_cfg = get_installed_config_path()
            port_cfg = get_portable_config_path()
            if os.path.isfile(inst_cfg):
                shutil.copy2(inst_cfg, port_cfg)
                try:
                    os.remove(inst_cfg)
                except Exception:
                    pass
        except Exception:
            pass

        # Schedule cleanup of the installed folder on exit
        schedule_self_delete(get_install_dir())
        return True, portable_exe
    except Exception as e:
        return False, str(e)


def remove_phantom_vpn_adapters() -> None:
    """
    Finds and completely uninstalls phantom / lingering virtual network adapters
    (Wintun, WireGuard, Amnezia, OpenConnect, TAP) via PowerShell and pnputil.
    """
    if not is_windows():
        return
    ps_cmd = (
        "$devs = @(Get-PnpDevice -Class Net -PresentOnly:$false -ErrorAction SilentlyContinue | "
        "Where-Object { $_.FriendlyName -match 'Wintun|WireGuard|Amnezia|OpenConnect|TAP' -or $_.InstanceId -match 'WINTUN' }); "
        "$devs += @(Get-PnpDevice -Class Net -ErrorAction SilentlyContinue | "
        "Where-Object { $_.FriendlyName -match 'Wintun|WireGuard|Amnezia|OpenConnect|TAP' -or $_.InstanceId -match 'WINTUN' }); "
        "$devs | Select-Object -ExpandProperty InstanceId -Unique | ForEach-Object { pnputil /remove-device $_ }"
    )
    try:
        kwargs = {
            "capture_output": True,
            "timeout": 20
        }
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        else:
            kwargs["creationflags"] = 0x08000000

        subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
            **kwargs
        )
    except Exception:
        pass


def full_system_uninstall() -> Tuple[bool, str]:
    """
    Completely removes BobrDobr from the machine:
    - Desktop and Start Menu shortcuts
    - Firewall rule
    - Lingering and phantom virtual network adapters (Wintun / WireGuard)
    - Settings and profiles (%APPDATA%/BobrDobr)
    - Persistent binaries (%LOCALAPPDATA%/BobrDobr)
    - Schedules deletion of installed program files (%LOCALAPPDATA%/Programs/BobrDobr)
    """
    if not is_windows():
        return False, "Поддерживается только в Windows."

    try:
        # 1. Clear in-memory config store immediately so exit hooks cannot resurrect settings.json
        try:
            from utils.config_store import settings
            settings.clear()
        except Exception:
            pass

        # 2. Remove shortcuts
        for lnk in [get_desktop_shortcut_path(), get_start_menu_shortcut_path()]:
            if os.path.isfile(lnk):
                try:
                    os.remove(lnk)
                except Exception:
                    pass

        # 3. Remove firewall rule
        remove_firewall_rule()

        # 4. Remove phantom / lingering virtual VPN network adapters
        remove_phantom_vpn_adapters()

        # 4. Remove AppData/Roaming/BobrDobr (settings and profiles)
        appdata = os.environ.get("APPDATA")
        if not appdata:
            appdata = os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
        roaming_dir = os.path.join(appdata, "BobrDobr")
        if os.path.isdir(roaming_dir):
            try:
                shutil.rmtree(roaming_dir, ignore_errors=True)
            except Exception:
                pass

        # 5. Remove AppData/Local/BobrDobr (persistent binaries and Wintun)
        local_appdata = os.environ.get("LOCALAPPDATA")
        if not local_appdata:
            local_appdata = os.path.join(os.path.expanduser("~"), "AppData", "Local")
        local_bin_dir = os.path.join(local_appdata, "BobrDobr")
        if os.path.isdir(local_bin_dir):
            try:
                shutil.rmtree(local_bin_dir, ignore_errors=True)
            except Exception:
                pass

        # 6. Remove temporary VPN configs from %TEMP% (awg_*.conf)
        try:
            import tempfile
            import glob
            temp_dir = tempfile.gettempdir()
            for conf_file in glob.glob(os.path.join(temp_dir, "awg_*.conf")):
                try:
                    os.remove(conf_file)
                except Exception:
                    pass
        except Exception:
            pass

        # 7. Schedule deletion of installed executable directory
        install_dir = get_install_dir()
        schedule_self_delete(install_dir)

        return True, "Все компоненты БобрДобр успешно удалены из системы."
    except Exception as e:
        return False, str(e)


def schedule_self_delete(target_dir: str) -> None:
    """
    Launches an independent background cleanup script that:
    1. Patiently waits for the calling process (PID) to fully terminate.
    2. Repeatedly attempts to delete target_dir for up to 40 retries.
    3. Cleans up itself upon completion.
    Uses 'ping' instead of 'timeout' to avoid 'Input redirection is not supported' errors.
    """
    if not is_windows():
        return
    clean_dir = os.path.abspath(target_dir)
    if not os.path.exists(clean_dir):
        return

    pid = os.getpid()
    temp_dir = os.environ.get("TEMP", os.path.expanduser("~"))
    bat_path = os.path.join(temp_dir, f"bobrdobr_cleanup_{pid}_{uuid.uuid4().hex[:6]}.bat")

    bat_content = f"""@echo off
set "TARGET={clean_dir}"
set "PID={pid}"

:wait_pid
tasklist /fi "PID eq %PID%" 2>nul | findstr /i "%PID%" >nul 2>&1
if not errorlevel 1 (
    ping 127.0.0.1 -n 2 >nul 2>&1
    goto wait_pid
)

ping 127.0.0.1 -n 2 >nul 2>&1

for /l %%i in (1,1,40) do (
    if not exist "%TARGET%" goto done
    del /f /q "%TARGET%\\BobrDobr-VPN.exe" >nul 2>&1
    del /f /q /s "%TARGET%\\*.*" >nul 2>&1
    rmdir /s /q "%TARGET%" >nul 2>&1
    if not exist "%TARGET%" goto done
    ping 127.0.0.1 -n 2 >nul 2>&1
)

:done
(goto) 2>nul & del "%~f0" >nul 2>&1
"""

    try:
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(bat_content)

        kwargs = {
            "close_fds": True,
            "creationflags": (
                subprocess.CREATE_NO_WINDOW
                if hasattr(subprocess, "CREATE_NO_WINDOW")
                else 0x08000000
            )
        }
        subprocess.Popen(["cmd.exe", "/c", bat_path], **kwargs)
    except Exception as e:
        print(f"Warning: could not schedule self delete: {e}")
