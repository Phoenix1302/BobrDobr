//go:build windows

package vpn

import (
	"fmt"
	"net"
	"os/exec"
	"strings"

	"golang.org/x/sys/windows"
)

// GetPhysicalDefaultGateway is a standalone utility function that detects the active physical default gateway.
func GetPhysicalDefaultGateway() (string, error) {
	rm := NewRouteManager()
	return rm.DetectPhysicalGateway()
}

// GetPhysicalDefaultGatewayAndInterface returns both the gateway IP and interface index.
func GetPhysicalDefaultGatewayAndInterface() (string, int, error) {
	rm := NewRouteManager()
	gw, err := rm.DetectPhysicalGateway()
	if err != nil {
		return "", 0, err
	}
	return gw, rm.CachedInterfaceIndex(), nil
}

// defaultInterfaceFinder maps an interface IP to its system interface index on Windows.
func defaultInterfaceFinder(targetIP string) int {
	ifaces, err := net.Interfaces()
	if err != nil {
		return 0
	}
	for _, ifi := range ifaces {
		addrs, err := ifi.Addrs()
		if err != nil {
			continue
		}
		for _, addr := range addrs {
			var ip net.IP
			switch v := addr.(type) {
			case *net.IPNet:
				ip = v.IP
			case *net.IPAddr:
				ip = v.IP
			}
			if ip != nil && ip.To4() != nil && ip.To4().String() == targetIP {
				return ifi.Index
			}
		}
	}
	return 0
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
