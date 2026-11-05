import os
import re
from typing import Optional, List, Dict, Any
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
        self.connect_url: str = ""
        self.group: str = ""

    def start_connection(
        self,
        server: str,
        port: int = 443,
        username: str = "",
        password: str = "",
        protocol: str = "anyconnect",
        allow_insecure_cert: bool = False,
        camouflage_secret: str = "",
        connect_url: str = "",
        group: str = "",
        extra_args: Optional[List[str]] = None,
        **kwargs: Any
    ) -> bool:
        """
        Launches openconnect with --passwd-on-stdin to keep credentials private.
        Supports ocserv camouflage (traffic obfuscation masked behind a web service)
        and --authgroup routing.
        """
        if not server or not server.strip():
            self.error_occurred.emit("Server address is required!")
            return False

        if self.is_running() or self.state == VPNState.DISCONNECTING:
            self.log("Stopping previous OpenConnect connection asynchronously...", "sys")
            self.stop_connection(wait=False)

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
                kill_openconnect_daemons(only_this_app=True)
            except Exception:
                pass

        self.server = server.strip()
        self.port = port
        self.protocol = protocol
        self.username = username.strip()
        self.camouflage_secret = camouflage_secret.strip()
        self.connect_url = connect_url.strip() if connect_url else ""
        self.group = group.strip() if group else ""

        # Determine raw target string: connect_url takes precedence if provided
        if self.connect_url:
            raw_target = self.connect_url
            if raw_target.startswith("/"):
                raw_target = f"https://{self.server}{raw_target}"
        else:
            raw_target = self.server

        scheme = "https://"
        if raw_target.startswith("https://"):
            scheme = "https://"
            raw_target = raw_target[8:]
        elif raw_target.startswith("http://"):
            scheme = "http://"
            raw_target = raw_target[7:]
        elif raw_target.startswith("anyconnect://"):
            scheme = "https://"
            raw_target = raw_target[13:]

        # Separate query string if present
        query_part = ""
        if "?" in raw_target:
            raw_target, query_part = raw_target.split("?", 1)

        # Separate path if present
        path_part = ""
        if "/" in raw_target:
            host_port, path_part = raw_target.split("/", 1)
            path_part = "/" + path_part
        else:
            host_port = raw_target

        # Parse host and port cleanly without choking on path
        host = host_port
        target_port = self.port
        if ":" in host_port:
            parts = host_port.split(":", 1)
            host = parts[0]
            try:
                target_port = int(parts[1])
            except ValueError:
                pass

        # Handle camouflage secret / query / path
        # In ocserv AnyConnect protocol, camouflage is strictly expected as a query string: https://host:port/?secret
        active_camouflage = self.camouflage_secret
        if active_camouflage:
            camo_token = active_camouflage.strip().lstrip("/?")
            if camo_token:
                # If path_part was just the camouflage token passed in connect_url (e.g. /kurwa), strip path
                if path_part.strip("/") == camo_token:
                    path_part = ""
                query_part = camo_token
        elif path_part and not query_part:
            # Fallback: if server sent a single-token path without query (e.g. /kurwa), treat as camouflage query
            stripped_path = path_part.strip("/")
            if stripped_path and "/" not in stripped_path and not stripped_path.endswith((".xml", ".html", ".php", ".jsp")):
                query_part = stripped_path
                path_part = ""

        # Build host with port (omit standard 443 if standard)
        if target_port and target_port != 443:
            host_with_port = f"{host}:{target_port}"
        else:
            host_with_port = host

        clean_path = path_part.rstrip("/") if path_part else ""
        if clean_path and clean_path != "/":
            base_url = f"{scheme}{host_with_port}{clean_path}"
        else:
            base_url = f"{scheme}{host_with_port}"

        if query_part:
            if clean_path and clean_path != "/":
                server_target = f"{base_url}?{query_part}"
            else:
                server_target = f"{base_url}/?{query_part}"
        else:
            server_target = base_url

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

        if self.group:
            cmd.extend(["--authgroup", self.group])

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

        cam_info = f" [Camouflage active: {clean_path or ('?' + query_part if query_part else '')}]" if (clean_path or query_part) else ""
        group_info = f" [Group: {self.group}]" if self.group else ""
        self.log(f"Initiating OpenConnect: protocol={self.protocol}, server={server_target}{cam_info}{group_info}, user={self.username or '<empty>'}", "sys")

        # Start process with password passed safely via stdin
        return self._spawn_process(cmd=cmd, stdin_data=password)

    def stop_connection(self, wait: bool = False) -> None:
        """Stops OpenConnect tunnel and cleanly disconnects, allowing the AnyConnect BYE packet to be sent."""
        target_proc = self._process
        stop_token = self._session_run_id
        super().stop_connection(wait=wait)
        if is_windows() and not wait:
            def cleanup_worker():
                # Asynchronously monitor target_proc exit without arbitrary time.sleep
                if target_proc is not None:
                    try:
                        target_proc.wait(timeout=5.0)
                    except Exception:
                        pass

                # Never kill daemons if user has already initiated a new connection or is connected
                if self._session_run_id != stop_token:
                    return
                if self.state in (VPNState.CONNECTING, VPNState.CONNECTED):
                    return
                if self._process is not None and self._process is not target_proc:
                    return
                if self.is_running():
                    return

                # If the specific target process did not terminate, kill it by PID
                if target_proc is not None and target_proc.poll() is None:
                    try:
                        target_proc.kill()
                    except Exception:
                        pass
                    run_silent_cmd(["taskkill", "/F", "/T", "/PID", str(target_proc.pid)], timeout=2)
                elif self.state == VPNState.DISCONNECTED and not self.is_running():
                    kill_openconnect_daemons(only_this_app=True)

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
            "user canceled",
            "user detached",
            "logout complete",
            "bye"
        ]):
            if any(k in lower for k in [
                "session terminated", "user canceled", "user detached",
                "logout complete", "bye"
            ]):
                self.set_state(VPNState.DISCONNECTED)
            else:
                self.set_state(VPNState.ERROR)
                self.error_occurred.emit(line)
