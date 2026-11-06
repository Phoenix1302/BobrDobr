//go:build windows

package vpn

import (
	"fmt"
	"os/exec"
	"strings"

	"golang.org/x/sys/windows"
)

// GetPhysicalDefaultGateway is a standalone utility function that detects the active physical default gateway.
func GetPhysicalDefaultGateway() (string, error) {
	rm := NewRouteManager()
	return rm.DetectPhysicalGateway()
}

// defaultRouteExecutor executes "route.exe" silently with windows.CREATE_NO_WINDOW
func defaultRouteExecutor(args ...string) error {
	cmd := exec.Command("route", args...)
	cmd.SysProcAttr = &windows.SysProcAttr{
		HideWindow:    true,
		CreationFlags: windows.CREATE_NO_WINDOW,
	}
	output, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("route %s failed (%w): %s", strings.Join(args, " "), err, strings.TrimSpace(string(output)))
	}
	return nil
}

// defaultCmdRunner executes a command silently and returns output
func defaultCmdRunner(name string, args ...string) (string, error) {
	cmd := exec.Command(name, args...)
	cmd.SysProcAttr = &windows.SysProcAttr{
		HideWindow:    true,
		CreationFlags: windows.CREATE_NO_WINDOW,
	}
	output, err := cmd.CombinedOutput()
	if err != nil {
		return string(output), fmt.Errorf("%s %s failed (%w): %s", name, strings.Join(args, " "), err, strings.TrimSpace(string(output)))
	}
	return string(output), nil
}
