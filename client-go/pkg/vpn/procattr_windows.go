//go:build windows

package vpn

import (
	"os/exec"

	"golang.org/x/sys/windows"
)

// configureSysProcAttr configures execution attributes for VPN daemon processes (AmneziaWG, OpenConnect).
// A new console is allocated with CREATE_NEW_CONSOLE | CREATE_NEW_PROCESS_GROUP.
// Note: CREATE_NO_WINDOW must NOT be used because it prevents allocating a console,
// which causes AttachConsole to fail with ERROR_INVALID_HANDLE (6) and prevents delivering
// CTRL_C_EVENT or CTRL_BREAK_EVENT.
// HideWindow: true sets STARTF_USESHOWWINDOW with SW_HIDE so the console window remains completely hidden.
func configureSysProcAttr(cmd *exec.Cmd) {
	cmd.SysProcAttr = &windows.SysProcAttr{
		HideWindow:    true,
		CreationFlags: windows.CREATE_NEW_CONSOLE | windows.CREATE_NEW_PROCESS_GROUP,
	}
}
