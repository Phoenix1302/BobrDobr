//go:build !windows

package gui

// SetAutoStart is a no-op on non-Windows platforms.
func SetAutoStart(enabled bool) error {
	return nil
}

// IsAutoStartEnabled returns false on non-Windows platforms.
func IsAutoStartEnabled() bool {
	return false
}
