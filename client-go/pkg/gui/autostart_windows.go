//go:build windows

package gui

import (
	"fmt"
	"os"

	"golang.org/x/sys/windows/registry"
)

const (
	runRegistryKey             = `Software\Microsoft\Windows\CurrentVersion\Run`
	startupApprovedRegistryKey = `Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run`
	runValueName               = "BobrDobrVPN"
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
		if err := k.SetStringValue(runValueName, val); err != nil {
			return err
		}

		// Update StartupApproved in Windows Explorer to guarantee Task Manager shows it as "Enabled"
		if approvedKey, err := registry.OpenKey(registry.CURRENT_USER, startupApprovedRegistryKey, registry.SET_VALUE); err == nil {
			defer approvedKey.Close()
			// 0x02 = Enabled in Windows 10/11 Task Manager
			enabledBytes := []byte{0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00}
			_ = approvedKey.SetBinaryValue(runValueName, enabledBytes)
		}
		return nil
	}

	// Delete value if exists
	_ = k.DeleteValue(runValueName)

	if approvedKey, err := registry.OpenKey(registry.CURRENT_USER, startupApprovedRegistryKey, registry.SET_VALUE); err == nil {
		defer approvedKey.Close()
		_ = approvedKey.DeleteValue(runValueName)
	}
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
