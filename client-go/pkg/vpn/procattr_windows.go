//go:build windows

package vpn

import (
	"os/exec"

	"golang.org/x/sys/windows"
)

// configureAmneziaProcAttr configures execution attributes for AmneziaWG daemon.
// AmneziaWG (WireGuard) is a stateless UDP protocol with no session state or CSTP disconnect requirements.
// CREATE_NO_WINDOW completely eliminates the console window (conhost.exe), ensuring 100% hidden execution.
func configureAmneziaProcAttr(cmd *exec.Cmd) {
	cmd.SysProcAttr = &windows.SysProcAttr{
		HideWindow:    true,
		CreationFlags: windows.CREATE_NO_WINDOW | windows.CREATE_NEW_PROCESS_GROUP,
	}
}

// configureOpenConnectProcAttr configures execution attributes for OpenConnect daemon.
// Pure-Go openconnect-worker runs completely headless with CREATE_NO_WINDOW, eliminating any conhost.exe
// console window or flashing. Graceful termination is managed via standard input pipe closure (EOF / STOP)
// or native context cancellation.
// HideWindow: true sets STARTF_USESHOWWINDOW/SW_HIDE to guarantee 100% hidden execution.
func configureOpenConnectProcAttr(cmd *exec.Cmd) {
	cmd.SysProcAttr = &windows.SysProcAttr{
		HideWindow:    true,
		CreationFlags: windows.CREATE_NO_WINDOW | windows.CREATE_NEW_PROCESS_GROUP,
	}
}
