import os
import sys
import time
import signal
import subprocess
import threading
from abc import abstractmethod
from enum import Enum
from typing import Optional, List, Dict, Any
from PySide6.QtCore import QObject, Signal

from utils.platform_helper import is_windows, is_linux, run_silent_cmd


class VPNState(str, Enum):
    DISCONNECTED = "Disconnected"
    CONNECTING = "Connecting"
    CONNECTED = "Connected"
    DISCONNECTING = "Disconnecting"
    ERROR = "Error"


class VPNLauncherBase(QObject):
    """
    Abstract base class for VPN process orchestration.
    Provides standard Qt signals for UI updates, real-time log streaming,
    and cross-platform graceful subprocess lifecycle management.
    """
    state_changed = Signal(str)            # VPNState value
    log_received = Signal(str, str)        # message, channel ("stdout" | "stderr" | "sys")
    error_occurred = Signal(str)          # error description

    def __init__(self, name: str, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.name = name
        self._state: VPNState = VPNState.DISCONNECTED
        self._process: Optional[subprocess.Popen] = None
        self._stop_requested = threading.Event()
        self._reader_threads: List[threading.Thread] = []

    @property
    def state(self) -> VPNState:
        return self._state

    def set_state(self, new_state: VPNState) -> None:
        if self._state != new_state:
            self._state = new_state
            self.state_changed.emit(new_state.value)
            self.log_received.emit(f"[{self.name}] State changed to: {new_state.value}", "sys")

    def log(self, message: str, channel: str = "sys") -> None:
        self.log_received.emit(f"[{self.name}] {message.strip()}", channel)

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @abstractmethod
    def start_connection(self, **kwargs: Any) -> bool:
        """Start the VPN connection with protocol-specific parameters."""
        pass

    def stop_connection(self, wait: bool = False) -> None:
        """Gracefully disconnects and cleans up network tunnels."""
        if not self.is_running():
            self.set_state(VPNState.DISCONNECTED)
            return

        self.set_state(VPNState.DISCONNECTING)
        self._stop_requested.set()
        self.log("Initiating graceful shutdown...", "sys")

        proc = self._process
        if proc is None:
            self.set_state(VPNState.DISCONNECTED)
            return

        def shutdown_worker():
            try:
                pid = proc.pid
                if is_windows():
                    # 1. Graceful break signal (triggers Go and Wintun adapter teardown)
                    try:
                        proc.send_signal(signal.CTRL_BREAK_EVENT)
                    except Exception:
                        try:
                            proc.terminate()
                        except Exception:
                            pass
                    try:
                        proc.wait(timeout=2.0)
                        self.log("Process terminated cleanly.", "sys")
                    except subprocess.TimeoutExpired:
                        try:
                            proc.terminate()
                            proc.wait(timeout=1.0)
                        except Exception:
                            pass
                        run_silent_cmd(["taskkill", "/F", "/T", "/PID", str(pid)], timeout=2)
                        try:
                            proc.wait(timeout=1.0)
                        except Exception:
                            pass
                else:
                    # On Linux, send SIGINT / SIGTERM to the process group
                    try:
                        pgid = os.getpgid(pid)
                        os.killpg(pgid, signal.SIGINT)
                    except Exception:
                        proc.terminate()

                    try:
                        proc.wait(timeout=3.0)
                        self.log("Process terminated cleanly.", "sys")
                    except subprocess.TimeoutExpired:
                        self.log("Process did not exit within timeout, forcing termination...", "sys")
                        try:
                            pgid = os.getpgid(pid)
                            os.killpg(pgid, signal.SIGKILL)
                        except Exception:
                            proc.kill()
                        proc.wait(timeout=2.0)
                    else:
                        try:
                            pgid = os.getpgid(pid)
                            os.killpg(pgid, signal.SIGKILL)
                        except Exception:
                            proc.kill()
                    proc.wait(timeout=2.0)
            except Exception as e:
                self.log(f"Error during shutdown: {e}", "sys")
            finally:
                self._process = None
                self.set_state(VPNState.DISCONNECTED)

        if wait:
            shutdown_worker()
        else:
            threading.Thread(target=shutdown_worker, daemon=True).start()

    def _spawn_process(
        self,
        cmd: List[str],
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        stdin_data: Optional[str] = None
    ) -> bool:
        """Spawns binary in an isolated subprocess with realtime stdout/stderr streaming."""
        if self.is_running():
            self.log("Process is already running.", "sys")
            return False

        self._stop_requested.clear()
        self.set_state(VPNState.CONNECTING)

        process_env = os.environ.copy()
        if env:
            process_env.update(env)

        creationflags = 0
        preexec = None

        startupinfo = None
        if is_windows():
            # CREATE_NEW_PROCESS_GROUP is required for graceful CTRL_BREAK_EVENT
            # CREATE_NO_WINDOW prevents black console windows from opening
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
            if hasattr(subprocess, "CREATE_NO_WINDOW"):
                creationflags |= subprocess.CREATE_NO_WINDOW
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
        elif is_linux():
            preexec = os.setsid

        try:
            self.log(f"Executing: {' '.join(cmd[:2])} [args omitted for security]", "sys")
            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE if stdin_data is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                cwd=cwd,
                env=process_env,
                creationflags=creationflags,
                startupinfo=startupinfo,
                preexec_fn=preexec,
                encoding="utf-8",
                errors="replace"
            )

            # If sensitive stdin data (like password) is provided, stream it and close stdin
            if stdin_data is not None and self._process.stdin:
                try:
                    self._process.stdin.write(stdin_data)
                    if not stdin_data.endswith("\n"):
                        self._process.stdin.write("\n")
                    self._process.stdin.flush()
                    self._process.stdin.close()
                except Exception as e:
                    self.log(f"Failed to pass data to stdin: {e}", "sys")

            # Start background reader threads for stdout and stderr
            t_out = threading.Thread(target=self._stream_reader, args=(self._process.stdout, "stdout"), daemon=True)
            t_err = threading.Thread(target=self._stream_reader, args=(self._process.stderr, "stderr"), daemon=True)
            t_wait = threading.Thread(target=self._monitor_exit, args=(self._process,), daemon=True)

            self._reader_threads = [t_out, t_err, t_wait]
            t_out.start()
            t_err.start()
            t_wait.start()

            return True

        except FileNotFoundError:
            err_msg = f"Binary executable not found: {cmd[0]}"
            self.log(err_msg, "error")
            self.error_occurred.emit(err_msg)
            self.set_state(VPNState.ERROR)
            return False
        except PermissionError:
            err_msg = f"Insufficient permissions to run {cmd[0]}. Please run as administrator/root."
            self.log(err_msg, "error")
            self.error_occurred.emit(err_msg)
            self.set_state(VPNState.ERROR)
            return False
        except Exception as e:
            err_msg = f"Failed to start process: {str(e)}"
            self.log(err_msg, "error")
            self.error_occurred.emit(err_msg)
            self.set_state(VPNState.ERROR)
            return False

    def _stream_reader(self, pipe, channel_name: str) -> None:
        """Reads stream line-by-line and triggers parse_log_line."""
        if not pipe:
            return
        try:
            for line in iter(pipe.readline, ""):
                if not line:
                    break
                stripped = line.rstrip()
                if stripped:
                    self.log_received.emit(stripped, channel_name)
                    self._parse_log_line(stripped, channel_name)
        except Exception as e:
            if not self._stop_requested.is_set():
                self.log(f"Reader exception on {channel_name}: {e}", "sys")
        finally:
            try:
                pipe.close()
            except Exception:
                pass

    def _monitor_exit(self, proc: subprocess.Popen) -> None:
        """Monitors process exit code."""
        ret = proc.wait()
        if self._stop_requested.is_set():
            self.set_state(VPNState.DISCONNECTED)
            self._process = None
            return

        if ret == 0:
            self.log(f"Process exited normally with code {ret}", "sys")
            self.set_state(VPNState.DISCONNECTED)
        else:
            self.log(f"Process terminated unexpectedly with exit code {ret}", "error")
            self.set_state(VPNState.ERROR)
        self._process = None

    @abstractmethod
    def _parse_log_line(self, line: str, channel: str) -> None:
        """Protocol-specific state parser."""
        pass
