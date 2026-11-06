//go:build windows

package gui

import (
	"os"
	"strings"

	"golang.org/x/sys/windows"
)

// IsElevated returns true if the current process is running with Administrator privileges.
func IsElevated() bool {
	token := windows.GetCurrentProcessToken()
	return token.IsElevated()
}

// RelaunchAsAdmin restarts the application with UAC Administrator elevation.
func RelaunchAsAdmin() error {
	exe, err := os.Executable()
	if err != nil {
		return err
	}
	cwd, _ := os.Getwd()
	var argStr string
	if len(os.Args) > 1 {
		argStr = strings.Join(os.Args[1:], " ")
	}

	verbPtr, _ := windows.UTF16PtrFromString("runas")
	exePtr, _ := windows.UTF16PtrFromString(exe)
	cwdPtr, _ := windows.UTF16PtrFromString(cwd)
	var argsPtr *uint16
	if argStr != "" {
		argsPtr, _ = windows.UTF16PtrFromString(argStr)
	}

	return windows.ShellExecute(0, verbPtr, exePtr, argsPtr, cwdPtr, windows.SW_SHOWNORMAL)
}
