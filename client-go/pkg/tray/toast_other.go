//go:build !windows

package tray

// ShowToastWithAction is a no-op stub for non-Windows platforms.
func ShowToastWithAction(aumid, title, message, buttonText, protocolArg string) error {
	return nil
}
