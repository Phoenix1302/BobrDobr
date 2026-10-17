import os
import re
from typing import Optional, List, Dict
from core.vpn_manager import VPNLauncherBase, VPNState
from utils.platform_helper import (
    find_binary, is_windows, is_linux, get_base_dir, get_persistent_bin_dir,
    kill_openconnect_daemons
)


class OpenConnectLauncher(VPNLauncherBase):
    """
    Launcher and orchestrator for OpenConnect CLI client.
    Supports multiple SSL/TLS VPN protocols: Cisco AnyConnect, Pulse Secure,
    Palo Alto GlobalProtect, Juniper NC, F5, Fortinet.
    Secures credentials by streaming passwords strictly through stdin (never in process arguments).
    """

    SUPPORTED_PROTOCOLS = {
        "anyconnect": "Cisco AnyConnect (Default)",
        "pulse": "Pulse Secure / Ivanti",
        "gp": "Palo Alto GlobalProtect",
        "nc": "Juniper Network Connect",
        "f5": "F5 BIG-IP",
        "fortinet": "Fortinet FortiGate",
        "array": "Array Networks"
    }

    def __init__(self, parent=None):
        super().__init__(name="OpenConnect", parent=parent)
        self.server: str = ""
        self.port: int = 443
        self.protocol: str = "anyconnect"
        self.username: str = ""
        self.camouflage_secret: str = ""

    def start_connection(
        self,
        server: str,
        port: int = 443,
        username: str = "",
        password: str = "",
        protocol: str = "anyconnect",
        allow_insecure_cert: bool = False,
        camouflage_secret: str = "",
        extra_args: Optional[List[str]] = None
    ) -> bool:
        """
        Launches openconnect with --passwd-on-stdin to keep credentials private.
        Supports ocserv camouflage (traffic obfuscation masked behind a web service).
        """
        if not server or not server.strip():
            self.error_occurred.emit("Server address is required!")
            return False

        binary = find_binary("openconnect")
        if not binary:
            msg = (
                "Executable 'openconnect' not found! "
                "Place 'openconnect.exe' (and required DLLs) into 'bin/windows/' or "
                "install openconnect on Linux (e.g. apt install openconnect)."
            )
            self.log(msg, "error")
            self.error_occurred.emit(msg)
            self.set_state(VPNState.ERROR)
            return False

        if is_windows():
            try:
                kill_openconnect_daemons()
            except Exception:
                pass

        self.server = server.strip()
        self.port = port
        self.protocol = protocol
        self.username = username.strip()
        self.camouflage_secret = camouflage_secret.strip()

        # Build clean server URL with host, port, and optional camouflage
        clean_server = self.server
        scheme = "https://"
        if clean_server.startswith("https://"):
            clean_server = clean_server[8:]
        elif clean_server.startswith("http://"):
            scheme = "http://"
            clean_server = clean_server[7:]

        # Check if URL already contained a query / camouflage string (e.g. ?secret_token)
        query_part = ""
        if "?" in clean_server:
            clean_server, query_part = clean_server.split("?", 1)

        active_camouflage = self.camouflage_secret if self.camouflage_secret else query_part
        clean_server = clean_server.rstrip("/")

        # Check if custom port was embedded in host string
        host = clean_server
        target_port = self.port
        if ":" in clean_server:
            parts = clean_server.split(":", 1)
            host = parts[0]
            try:
                target_port = int(parts[1])
            except ValueError:
                pass

        if target_port and target_port != 443:
            host_with_port = f"{host}:{target_port}"
        else:
            host_with_port = host

        # Construct final target
        if active_camouflage:
            server_target = f"{scheme}{host_with_port}/?{active_camouflage}"
        else:
            server_target = f"{scheme}{host_with_port}"

        # Construct safe command arguments
        cmd = [binary]

        # In OpenConnect, AnyConnect is the default protocol; pass --protocol only for non-default
        if self.protocol and self.protocol.lower() != "anyconnect":
            cmd.extend(["--protocol", self.protocol])

        cmd.extend([
            "--non-inter",
            "--passwd-on-stdin",  # Crucial security requirement: read password from pipe
            "-v"  # Real-time detailed connection logging
        ])

        if self.username:
            cmd.extend(["--user", self.username])

        # In OpenConnect v9+, --no-cert-check was removed upstream as insecure.
        # Standard system CA validation is enabled by default and validates trusted certificates.
        if allow_insecure_cert:
            self.log("Note: OpenConnect v9 validates against system trust store. If using self-signed certs, specify fingerprint in extra args.", "sys")

        # Locate vpnc-script if available
        vpnc_script = self._find_vpnc_script()
        if vpnc_script:
            cmd.extend(["--script", vpnc_script])
            self.log(f"Using VPNC script: {vpnc_script}", "sys")

        if extra_args:
            cmd.extend(extra_args)

        # Target server must be the last argument
        cmd.append(server_target)

        cam_info = f" [Camouflage active: ?{active_camouflage}]" if active_camouflage else ""
        self.log(f"Initiating OpenConnect: protocol={self.protocol}, server={server_target}{cam_info}, user={self.username or '<empty>'}", "sys")

        # Start process with password passed safely via stdin
        return self._spawn_process(cmd=cmd, stdin_data=password)

    def stop_connection(self, wait: bool = False) -> None:
        """Stops OpenConnect tunnel and cleans up lingering processes."""
        super().stop_connection(wait=wait)
        if is_windows():
            def cleanup_worker():
                if not wait:
                    import time
                    time.sleep(0.3)
                kill_openconnect_daemons()

            if wait:
                cleanup_worker()
            else:
                import threading
                threading.Thread(target=cleanup_worker, daemon=True).start()

    def _find_vpnc_script(self) -> Optional[str]:
        """Locates vpnc-script, vpnc-script-win.js or vpnc-script.js."""
        base_dir = get_base_dir()
        persistent_dir = get_persistent_bin_dir()
        script_names = ["vpnc-script.js", "vpnc-script-win.js"] if is_windows() else ["vpnc-script"]
        candidates = []
        for sname in script_names:
            candidates.extend([
                os.path.join(persistent_dir, sname),
                os.path.join(base_dir, "bin", "windows" if is_windows() else "linux", sname),
                os.path.join(base_dir, "bin", sname),
                os.path.join(base_dir, sname),
                os.path.join(os.getcwd(), "bin", "windows" if is_windows() else "linux", sname),
                f"/etc/vpnc/{sname}" if is_linux() else None,
                f"/usr/share/vpnc-scripts/{sname}" if is_linux() else None,
            ])
        for c in candidates:
            if c and os.path.isfile(c):
                return os.path.abspath(c)
        return None

    def _parse_log_line(self, line: str, channel: str) -> None:
        """Parses OpenConnect logs to determine connection state."""
        lower = line.lower()

        # Connecting indicators
        if any(keyword in lower for keyword in [
            "attempting to connect",
            "connected to https on",
            "got http response",
            "post https://"
        ]):
            if self.state != VPNState.CONNECTED:
                self.set_state(VPNState.CONNECTING)

        # Connected indicators
        elif any(keyword in lower for keyword in [
            "established dtls connection",
            "esp session established",
            "connected as",
            "configured as",
            "tunnel interface",
            "session established"
        ]):
            self.set_state(VPNState.CONNECTED)

        # Error / Disconnect indicators
        elif any(keyword in lower for keyword in [
            "authentication failed",
            "login failed",
            "failed to connect to host",
            "certificate validation failed",
            "unknown host",
            "connection refused",
            "session terminated",
            "user canceled"
        ]):
            if "session terminated" in lower or "user canceled" in lower:
                self.set_state(VPNState.DISCONNECTED)
            else:
                self.set_state(VPNState.ERROR)
                self.error_occurred.emit(line)
