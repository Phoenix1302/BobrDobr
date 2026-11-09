//go:build windows

package vpn

import (
	"golang.org/x/sys/windows"
)

var (
	kernel32DLL               = windows.NewLazySystemDLL("kernel32.dll")
	procSetConsoleCtrlHandler = kernel32DLL.NewProc("SetConsoleCtrlHandler")
	procFreeConsole           = kernel32DLL.NewProc("FreeConsole")
	procAttachConsole         = kernel32DLL.NewProc("AttachConsole")
)

// SendGracefulSignal sends a graceful termination signal to a console process on Windows.
// Attaches to the target process console so GenerateConsoleCtrlEvent can deliver CTRL_C_EVENT (SIGINT),
// triggering Wintun device unbinding in AmneziaWG and CSTP AnyConnect BYE packet in OpenConnect.
// If CTRL_C_EVENT fails, falls back to CTRL_BREAK_EVENT.
func SendGracefulSignal(pid int) bool {
	if pid <= 0 {
		return false
	}

	// Disable Ctrl-C handling in host GUI process while attached so it does not terminate
	procSetConsoleCtrlHandler.Call(0, 1)

	// A process can only be attached to at most one console at a time.
	// Detach from current console (if any) to ensure AttachConsole succeeds without ERROR_ACCESS_DENIED (5).
	procFreeConsole.Call()

	attached, _, _ := procAttachConsole.Call(uintptr(pid))
	if attached != 0 {
		defer func() {
			procFreeConsole.Call()
			// Re-enable handler when detached
			procSetConsoleCtrlHandler.Call(0, 0)
		}()

		// OpenConnect handles CTRL_C_EVENT as SIGINT and sends CSTP BYE packet.
		// CTRL_C_EVENT requires dwProcessGroupId = 0 when attached to target console.
		if err := windows.GenerateConsoleCtrlEvent(windows.CTRL_C_EVENT, 0); err == nil {
			return true
		}

		// Fallback to CTRL_BREAK_EVENT on the attached console
		if err := windows.GenerateConsoleCtrlEvent(windows.CTRL_BREAK_EVENT, 0); err == nil {
			return true
		}
	} else {
		// Re-enable handler if attach was unsuccessful
		procSetConsoleCtrlHandler.Call(0, 0)
	}

	// Fallback if AttachConsole was not successful
	err := windows.GenerateConsoleCtrlEvent(windows.CTRL_BREAK_EVENT, uint32(pid))
	return err == nil
}
