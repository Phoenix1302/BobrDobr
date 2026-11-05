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


def send_graceful_windows_signal(pid: int, proc: Optional[subprocess.Popen] = None) -> bool:
    """
    Sends a graceful CTRL_C_EVENT or CTRL_BREAK_EVENT to a console process on Windows.
    Attaches to the child process's console and issues GenerateConsoleCtrlEvent.
    This triggers OpenConnect's console_ctrl_handler to send the AnyConnect BYE packet,
    and AmneziaWG's Wintun cleanup.

    NOTE: SetConsoleCtrlHandler(None, True) is permanently maintained to protect
    the Python Qt GUI host process from asynchronous STATUS_CONTROL_C_EXIT crashes.
    """
    if not is_windows():
        return False
    if pid <= 0:
        return False
    if proc is not None and proc.poll() is not None:
        return False

    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        # Ensure calling Python GUI process permanently ignores console control events
        k32.SetConsoleCtrlHandler(None, True)
        k32.FreeConsole()
        if k32.AttachConsole(pid):
            try:
                k32.SetConsoleCtrlHandler(None, True)
                # Dispatch BOTH CTRL_C_EVENT (0) and CTRL_BREAK_EVENT (1)
                # OpenConnect catches CTRL_C_EVENT / CTRL_BREAK_EVENT to send the AnyConnect BYE packet.
                # AmneziaWG (Go runtime on Windows) specifically catches CTRL_BREAK_EVENT for graceful Wintun & route teardown.
                res_c = k32.GenerateConsoleCtrlEvent(0, 0)
                res_break = k32.GenerateConsoleCtrlEvent(1, 0)
                return bool(res_c or res_break)
            finally:
                k32.FreeConsole()
                # NEVER reset to False! Keep protection permanently active in GUI host process.
                k32.SetConsoleCtrlHandler(None, True)
    except Exception as e:
        print(f"[send_graceful_windows_signal] Failed to signal PID {pid}: {e}", file=sys.stderr)
    return False


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
        self._session_run_id: int = 0

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
        if self.is_running() and not self._stop_requested.is_set():
            self.log("Previous process is still active. Initiating non-blocking shutdown...", "sys")
            self.stop_connection(wait=False)
        return False

    def stop_connection(self, wait: bool = False) -> None:
        """Gracefully disconnects and cleans up network tunnels."""
        if not self.is_running() and self.state != VPNState.DISCONNECTING:
            self.set_state(VPNState.DISCONNECTED)
            return

        self.set_state(VPNState.DISCONNECTING)
        self._stop_requested.set()
        self.log("Initiating graceful shutdown...", "sys")

        proc_to_kill = self._process
        if proc_to_kill is None:
            self.set_state(VPNState.DISCONNECTED)
            return

        def shutdown_worker():
            try:
                if proc_to_kill.poll() is not None:
                    self.log(f"Process already exited with code {proc_to_kill.returncode}.", "sys")
                    return

                pid = proc_to_kill.pid
                if is_windows():
                    # 1. Graceful console control event (triggers OpenConnect AnyConnect BYE packet and Wintun cleanup)
                    signaled = False
                    if proc_to_kill.poll() is None:
                        signaled = send_graceful_windows_signal(pid, proc=proc_to_kill)
                    if signaled:
                        self.log(f"Sent graceful console control signal to PID {pid}.", "sys")
                    else:
                        if proc_to_kill.poll() is None:
                            try:
                                proc_to_kill.send_signal(signal.CTRL_BREAK_EVENT)
                                self.log(f"Sent CTRL_BREAK_EVENT fallback to PID {pid}.", "sys")
                            except Exception:
                                pass

                    # 2. Give process up to 6.0 seconds for graceful teardown (routes flush, WFP filters, Wintun unbind)
                    try:
                        proc_to_kill.wait(timeout=6.0)
                        self.log("Process terminated cleanly.", "sys")
                    except subprocess.TimeoutExpired:
                        if proc_to_kill.poll() is None:
                            self.log("Process did not exit within 6.0s timeout, attempting terminate...", "sys")
                            try:
                                proc_to_kill.terminate()
                                proc_to_kill.wait(timeout=1.5)
                            except (subprocess.TimeoutExpired, Exception):
                                pass

                        # Force termination via taskkill ONLY as a last resort if process really hung
                        if proc_to_kill.poll() is None:
                            self.log("Process is unresponsive, forcing termination with taskkill...", "sys")
                            run_silent_cmd(["taskkill", "/F", "/T", "/PID", str(pid)], timeout=3)
                            try:
                                proc_to_kill.wait(timeout=1.0)
                            except Exception:
                                pass
                        else:
                            self.log("Process terminated cleanly after terminate signal.", "sys")
                    except OSError:
                        # Process already terminated and handle invalidated
                        pass
                else:
                    # On Linux, send SIGINT / SIGTERM to the process group
                    try:
                        pgid = os.getpgid(pid)
                        os.killpg(pgid, signal.SIGINT)
                    except Exception:
                        proc_to_kill.terminate()

                    try:
                        proc_to_kill.wait(timeout=3.0)
                        self.log("Process terminated cleanly.", "sys")
                    except subprocess.TimeoutExpired:
                        self.log("Process did not exit within timeout, forcing termination...", "sys")
                        try:
                            pgid = os.getpgid(pid)
                            os.killpg(pgid, signal.SIGKILL)
                        except Exception:
                            proc_to_kill.kill()
                        try:
                            proc_to_kill.wait(timeout=2.0)
                        except Exception:
                            pass
            except Exception as e:
                # Ignore harmless handle errors when process already terminated
                if not (isinstance(e, OSError) and getattr(e, 'winerror', None) == 6):
                    self.log(f"Error during shutdown: {e}", "sys")
            finally:
                if self._process is proc_to_kill:
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
        # If previous process is still running, initiate asynchronous stop without blocking the UI thread
        if self.is_running():
            self.log("Stopping previous process asynchronously...", "sys")
            self.stop_connection(wait=False)

        self._stop_requested.clear()
        self._session_run_id += 1
        self.set_state(VPNState.CONNECTING)

        process_env = os.environ.copy()
        if env:
            process_env.update(env)

        creationflags = 0
        preexec = None

        startupinfo = None
        if is_windows():
            # CREATE_NEW_CONSOLE creates an isolated console attached to the child,
            # allowing AttachConsole + GenerateConsoleCtrlEvent to send graceful shutdown signals.
            # STARTF_USESHOWWINDOW with SW_HIDE guarantees the console window is completely hidden.
            creationflags = subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP
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
            curr_run_id = self._session_run_id
            t_out = threading.Thread(target=self._stream_reader, args=(self._process.stdout, "stdout", curr_run_id), daemon=True)
            t_err = threading.Thread(target=self._stream_reader, args=(self._process.stderr, "stderr", curr_run_id), daemon=True)
            t_wait = threading.Thread(target=self._monitor_exit, args=(self._process, curr_run_id), daemon=True)

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

    def _stream_reader(self, pipe, channel_name: str, run_id: Optional[int] = None) -> None:
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
                    if run_id is None or self._session_run_id == run_id:
                        self._parse_log_line(stripped, channel_name)
        except Exception as e:
            if not self._stop_requested.is_set():
                self.log(f"Reader exception on {channel_name}: {e}", "sys")
        finally:
            try:
                pipe.close()
            except Exception:
                pass

    def _monitor_exit(self, proc: subprocess.Popen, run_id: Optional[int] = None) -> None:
        """Monitors process exit code."""
        ret = proc.wait()
        if run_id is not None and self._session_run_id != run_id:
            return

        if self._stop_requested.is_set():
            if self._process is proc:
                self.set_state(VPNState.DISCONNECTED)
                self._process = None
            return

        if ret == 0:
            self.log(f"Process exited normally with code {ret}", "sys")
            if self._process is proc:
                self.set_state(VPNState.DISCONNECTED)
        else:
            self.log(f"Process terminated unexpectedly with exit code {ret}", "error")
            if self._process is proc:
                self.set_state(VPNState.ERROR)
        if self._process is proc:
            self._process = None

    @abstractmethod
    def _parse_log_line(self, line: str, channel: str) -> None:
        """Protocol-specific state parser."""
        pass
