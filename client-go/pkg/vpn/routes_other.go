//go:build !windows

package vpn

import (
	"errors"
)

// GetPhysicalDefaultGateway is a stub on non-Windows platforms.
func GetPhysicalDefaultGateway() (string, error) {
	return "", errors.New("not implemented on non-windows")
}

func defaultRouteExecutor(args ...string) error {
	return errors.New("not implemented on non-windows")
}

func defaultCmdRunner(name string, args ...string) (string, error) {
	return "", errors.New("not implemented on non-windows")
}
