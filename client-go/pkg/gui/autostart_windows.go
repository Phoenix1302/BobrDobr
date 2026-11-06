//go:build windows

package gui

import (
	"fmt"
	"os"

	"golang.org/x/sys/windows/registry"
)

const (
	runRegistryKey = `Software\Microsoft\Windows\CurrentVersion\Run`
	runValueName   = "BobrDobrVPN"
)

// SetAutoStart sets or removes the Windows user logon run entry for BobrDobr VPN.
func SetAutoStart(enabled bool) error {
	k, err := registry.OpenKey(registry.CURRENT_USER, runRegistryKey, registry.QUERY_VALUE|registry.SET_VALUE)
	if err != nil {
		return fmt.Errorf("failed to open Run registry key: %w", err)
	}
	defer k.Close()

	if enabled {
		exe, err := os.Executable()
		if err != nil {
			return err
		}
		val := fmt.Sprintf(`"%s" --minimized`, exe)
		return k.SetStringValue(runValueName, val)
	}

	// Delete value if exists
	_ = k.DeleteValue(runValueName)
	return nil
}

// IsAutoStartEnabled checks if the Windows user logon run entry exists.
func IsAutoStartEnabled() bool {
	k, err := registry.OpenKey(registry.CURRENT_USER, runRegistryKey, registry.QUERY_VALUE)
	if err != nil {
		return false
	}
	defer k.Close()

	_, _, err = k.GetStringValue(runValueName)
	return err == nil
}
