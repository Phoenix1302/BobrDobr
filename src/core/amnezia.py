import os
import re
import time
import configparser
import tempfile
import subprocess
from typing import Optional, Dict, Any
from core.vpn_manager import VPNLauncherBase, VPNState
from utils.platform_helper import (
    find_binary, get_wintun_path, is_windows, is_linux, run_silent_cmd,
    kill_amnezia_daemons, delete_wintun_adapter
)


class AmneziaWGLauncher(VPNLauncherBase):
    """
    Launcher and orchestrator for AmneziaWG (wireguard-go with custom packet header parameters).
    Handles .conf parsing, in-memory config persistence, parameter overrides,
    and process execution across Windows and Linux.
    """

    OBFUSCATION_KEYS = ["Jc", "Jmin", "Jmax", "S1", "S2", "H1", "H2", "H3", "H4"]

    def __init__(self, parent=None):
        super().__init__(name="AmneziaWG", parent=parent)
        self.config_path: Optional[str] = None
        self.interface_name: str = "awg0"
        self._temp_config: Optional[str] = None

    @classmethod
    def parse_config_text(cls, content: str) -> Dict[str, Any]:
        """
        Parses AmneziaWG .conf string content, extracting interface, peer,
        obfuscation parameters and shortcut gateway/IP fields.
        """
        parsed_data = {
            "interface": {},
            "peer": {},
            "obfuscation": {},
            "endpoint": "",
            "address": "",
            "dns": "",
            "allowed_ips": ""
        }

        current_section = None
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            if line.startswith("[") and line.endswith("]"):
                current_section = line[1:-1].strip().lower()
                continue

            if "=" in line and current_section:
                key, val = [p.strip() for p in line.split("=", 1)]
                if current_section == "interface":
                    if key in cls.OBFUSCATION_KEYS:
                        parsed_data["obfuscation"][key] = val
                    else:
                        parsed_data["interface"][key] = val
                elif current_section == "peer":
                    parsed_data["peer"][key] = val

        parsed_data["endpoint"] = parsed_data["peer"].get("Endpoint", "")
        parsed_data["address"] = parsed_data["interface"].get("Address", "")
        parsed_data["dns"] = parsed_data["interface"].get("DNS", "")
        parsed_data["allowed_ips"] = parsed_data["peer"].get("AllowedIPs", "")

        return parsed_data

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
        interface_name: str = "awg0"
    ) -> bool:
        """
        Prepares the tunnel configuration (directly from settings config_content or file),
        resolves binary & wintun.dll, and spawns the tunnel process.
        """
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
        self.interface_name = (interface_name or "").strip() or "awg0"

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

        try:
            # Windows: kill lingering daemons and delete stale adapter to prevent collision
            if is_windows():
                try:
                    kill_amnezia_daemons()
                    delete_wintun_adapter(self.interface_name)
                    time.sleep(0.3)
                except Exception:
                    pass

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

        super().stop_connection(wait=wait)

        if is_windows():
            def cleanup_worker():
                if not wait:
                    time.sleep(0.3)
                kill_amnezia_daemons()
                if self.interface_name:
                    delete_wintun_adapter(self.interface_name)

            if wait:
                cleanup_worker()
            else:
                import threading
                threading.Thread(target=cleanup_worker, daemon=True).start()

        if self._temp_config and os.path.exists(self._temp_config):
            try:
                os.remove(self._temp_config)
            except Exception:
                pass
            self._temp_config = None

    def _parse_log_line(self, line: str, channel: str) -> None:
        """Monitors stdout/stderr output for connection handshake and errors."""
        lower = line.lower()

        # Connected states
        if any(keyword in lower for keyword in [
            "device started",
            "interface created",
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
            "failed to setup wireguard",
            "wintun: unable to load",
            "permission denied",
            "address already in use"
        ]):
            self.set_state(VPNState.ERROR)
            self.error_occurred.emit(line)
