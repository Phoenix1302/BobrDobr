//go:build !windows

package gui

// IsElevated returns true on non-Windows platforms.
func IsElevated() bool {
	return true
}

// RelaunchAsAdmin is a no-op on non-Windows platforms.
func RelaunchAsAdmin() error {
	return nil
}
