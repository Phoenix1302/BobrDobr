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

// SendGracefulSignal sends a graceful CTRL_BREAK_EVENT to a console process on Windows.
// Triggers Wintun device unbinding in AmneziaWG and AnyConnect BYE packet in OpenConnect.
// It explicitly avoids attaching to the target console to prevent broadcasting Ctrl-C into the host GUI.
func SendGracefulSignal(pid int) bool {
	if pid <= 0 {
		return false
	}

	// Send process-group CTRL_BREAK_EVENT directly to target group without console attachment
	err := windows.GenerateConsoleCtrlEvent(windows.CTRL_BREAK_EVENT, uint32(pid))
	return err == nil
}
