import os
import re
import time
import configparser
import tempfile
import subprocess
from typing import Optional, Dict, Any
from core.vpn_manager import VPNLauncherBase, VPNState
from utils.conf_parser import parse_amnezia_config_text, OBFUSCATION_KEYS
from utils.platform_helper import (
    find_binary, get_wintun_path, is_windows, is_linux, run_silent_cmd,
    kill_amnezia_daemons, delete_wintun_adapter,
    is_process_running, is_network_adapter_present, get_wintun_device_instances,
    prepare_tunnel_adapter, get_next_available_tunnel_adapter, cleanup_stale_temp_configs,
    cleanup_orphan_bobrdobr_adapters
)


class AmneziaWGLauncher(VPNLauncherBase):
    """
    Launcher and orchestrator for AmneziaWG (wireguard-go with custom packet header parameters).
    Handles .conf parsing, in-memory config persistence, parameter overrides,
    and process execution across Windows and Linux.
    """

    OBFUSCATION_KEYS = OBFUSCATION_KEYS

    def __init__(self, parent=None):
        super().__init__(name="AmneziaWG", parent=parent)
        self.config_path: Optional[str] = None
        self.interface_name: str = "bobr0"
        self._temp_config: Optional[str] = None
        self._session_run_id: int = 0

    @classmethod
    def parse_config_text(cls, content: str) -> Dict[str, Any]:
        """
        Parses AmneziaWG .conf string content, extracting interface, peer,
        obfuscation parameters and shortcut gateway/IP fields.
        """
        return parse_amnezia_config_text(content)

    def parse_config(self, filepath: str) -> Dict[str, Any]:
        """
        Parses AmneziaWG .conf file from disk.
        """
        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"Config file not found: {filepath}")

        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        return self.parse_config_text(content)

    def start_connection(
        self,
        config_content: str = "",
        config_path: str = "",
        obfuscation_overrides: Optional[Dict[str, str]] = None,
        interface_name: str = "bobr0"
    ) -> bool:
        """
        Prepares the tunnel configuration (directly from settings config_content or file),
        resolves binary & wintun.dll, and spawns the tunnel process.
        """
        # If previous connection is still active and stop was not requested, soft stop it asynchronously
        if self.is_running() and not self._stop_requested.is_set():
            self.log("Stopping previous AmneziaWG connection asynchronously...", "sys")
            self.stop_connection(wait=False)

        active_config_path: Optional[str] = None

        # 1. Prefer in-memory config_content from settings
        if config_content and config_content.strip():
            final_content = config_content.strip()
            if obfuscation_overrides:
                final_content = self._apply_obfuscation_overrides(final_content, obfuscation_overrides)

            temp_fd, temp_path = tempfile.mkstemp(prefix="awg_", suffix=".conf")
            with os.fdopen(temp_fd, "w", encoding="utf-8") as tf:
                tf.write(final_content + "\n")
            self._temp_config = temp_path
            active_config_path = temp_path
            self.log("Tunnel configuration loaded from profile settings", "sys")

        # 2. Fallback to config_path if file exists
        elif config_path and os.path.isfile(config_path):
            with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            if obfuscation_overrides:
                content = self._apply_obfuscation_overrides(content, obfuscation_overrides)

            temp_fd, temp_path = tempfile.mkstemp(prefix="awg_", suffix=".conf")
            with os.fdopen(temp_fd, "w", encoding="utf-8") as tf:
                tf.write(content + "\n")
            self._temp_config = temp_path
            active_config_path = temp_path
            self.log(f"Tunnel configuration loaded from file: {config_path}", "sys")

        else:
            msg = (
                "Ошибка запуска AmneziaWG: параметры конфигурации отсутствуют!\n"
                "Откройте «⚙ Настройки» подключения и выберите или вставьте .conf файл."
            )
            self.log(msg, "error")
            self.error_occurred.emit(msg)
            self.set_state(VPNState.ERROR)
            return False

        self.config_path = active_config_path
        self.interface_name = (interface_name or "").strip() or "bobr0"

        # Locate executable
        binary = find_binary("amneziawg-go") or find_binary("awg-quick") or find_binary("wireguard")
        if not binary:
            msg = (
                "Executable 'amneziawg-go' (or 'awg-quick') not found! "
                "Place it in the 'bin/windows/' or 'bin/linux/' directory, or install it system-wide."
            )
            self.log(msg, "error")
            self.error_occurred.emit(msg)
            self.set_state(VPNState.ERROR)
            return False

        # Windows-specific: ensure wintun.dll is available
        extra_env = {}
        if is_windows():
            wintun = get_wintun_path()
            if wintun:
                wintun_dir = os.path.dirname(wintun)
                self.log(f"Found Wintun driver at: {wintun}", "sys")
                extra_env["PATH"] = f"{wintun_dir};{os.environ.get('PATH', '')}"
            else:
                self.log("WARNING: wintun.dll not found in bin/windows/. Tunnel creation may fail.", "sys")

        self._session_run_id += 1

        try:
            # Windows: select next available tunnel adapter via rotation & safe check before building cmd
            if is_windows():
                try:
                    assigned_iface = get_next_available_tunnel_adapter(self.interface_name)
                    if assigned_iface != self.interface_name:
                        self.log(
                            f"Адаптер '{self.interface_name}' ротирован/переключен на свободный интерфейс '{assigned_iface}'.",
                            "sys"
                        )
                    self.interface_name = assigned_iface

                    ok, ready_iface = prepare_tunnel_adapter(self.interface_name)
                    if ok and ready_iface != self.interface_name:
                        self.interface_name = ready_iface
                except Exception as e:
                    self.log(f"Предупреждение при подготовке адаптера: {e}", "sys")

            # Build command line
            cmd = self._build_cmd(binary, active_config_path, self.interface_name)

            self.log(f"Using AmneziaWG binary: {binary}", "sys")
            self.log(f"Interface name: {self.interface_name}", "sys")

            return self._spawn_process(cmd=cmd, env=extra_env)
        except Exception as e:
            err = f"Ошибка инициализации туннеля AmneziaWG: {e}"
            self.log(err, "error")
            self.error_occurred.emit(err)
            self.set_state(VPNState.ERROR)
            return False

    def _build_cmd(self, binary: str, config_file: str, interface: str):
        """Constructs CLI arguments based on available tool and OS."""
        bin_basename = os.path.basename(binary).lower()

        if "awg-quick" in bin_basename:
            return [binary, "up", config_file]

        if "wireguard" in bin_basename and is_windows():
            return [binary, "/installtunnelservice", config_file]

        # amneziawg-go user-space daemon
        if is_windows():
            return [binary, "-config", config_file, "-name", interface]
        else:
            return [binary, "-f", interface]

    def _apply_obfuscation_overrides(self, content: str, overrides: Dict[str, str]) -> str:
        """Injects or updates custom obfuscation parameters under [Interface]."""
        for key, val in overrides.items():
            if not val:
                continue
            pattern = re.compile(rf"^\s*{re.escape(key)}\s*=.*$", re.MULTILINE)
            if pattern.search(content):
                content = pattern.sub(f"{key} = {val}", content)
            else:
                content = re.sub(r"(\[Interface\])", rf"\1\n{key} = {val}", content, count=1, flags=re.IGNORECASE)
        return content

    def stop_connection(self, wait: bool = False) -> None:
        """Stops connection and cleans up temporary config files."""
        if is_linux() and self.config_path:
            awg_quick = find_binary("awg-quick")
            if awg_quick:
                try:
                    subprocess.run([awg_quick, "down", self.config_path], capture_output=True, timeout=5)
                except Exception:
                    pass

        target_proc = self._process
        target_iface = self.interface_name
        target_temp_cfg = self._temp_config
        self._temp_config = None
        super().stop_connection(wait=wait)

        stop_token = self._session_run_id
        if is_windows():
            def cleanup_worker():
                # Asynchronously monitor target_proc exit without arbitrary time.sleep
                if target_proc is not None:
                    try:
                        target_proc.wait(timeout=6.0)
                    except Exception:
                        pass

                # Clean up the temporary config of the stopped session safely
                if target_temp_cfg and os.path.exists(target_temp_cfg):
                    try:
                        os.remove(target_temp_cfg)
                    except Exception:
                        pass
                cleanup_stale_temp_configs()

                # If a new connection started in the meantime, abort device/daemon cleanup
                if self._session_run_id != stop_token:
                    return
                if self.state in (VPNState.CONNECTING, VPNState.CONNECTED):
                    return
                if self._process is not None and self._process is not target_proc:
                    return
                if self.is_running():
                    return
                if target_proc is not None and target_proc.poll() is None:
                    try:
                        target_proc.kill()
                    except Exception:
                        pass
                    run_silent_cmd(["taskkill", "/F", "/T", "/PID", str(target_proc.pid)], timeout=2)
                elif self.state == VPNState.DISCONNECTED and not self.is_running():
                    kill_amnezia_daemons(only_this_app=True)
                    if target_iface:
                        delete_wintun_adapter(target_iface)

            if wait:
                cleanup_worker()
            else:
                import threading
                threading.Thread(target=cleanup_worker, daemon=True).start()
        else:
            if target_temp_cfg and os.path.exists(target_temp_cfg):
                try:
                    os.remove(target_temp_cfg)
                except Exception:
                    pass
            cleanup_stale_temp_configs()

    def _parse_log_line(self, line: str, channel: str) -> None:
        """Monitors stdout/stderr output for connection handshake and errors."""
        lower = line.lower()

        # Connected states
        if any(keyword in lower for keyword in [
            "device started",
            "interface created",
            "interface bobr0 created",
            "interface bobr1 created",
            "interface awg0 created",
            "interface awg1 created",
            "interface awg2 created",
            f"interface {self.interface_name.lower()} created",
            "uapi: updating configuration",
            "receiving handshake response",
            "handshake for peer",
            "tunnel is up"
        ]):
            self.set_state(VPNState.CONNECTED)

        # Failure / Error states
        elif any(keyword in lower for keyword in [
            "unable to create interface",
            "unable to create wintun interface",
            "failed to setup adapter",
            "failed to setup wireguard",
            "wintun: unable to load",
            "timed out waiting for device query",
            "cannot create a file when that file already exists",
            "permission denied",
            "address already in use"
        ]):
            if is_windows() and any(k in lower for k in [
                "unable to create", "failed to setup adapter", "already in use",
                "already exists", "timed out waiting for device query"
            ]):
                try:
                    delete_wintun_adapter(self.interface_name)
                except Exception:
                    pass
            self.set_state(VPNState.ERROR)
            self.error_occurred.emit(line)
