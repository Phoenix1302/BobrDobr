//go:build !windows

package gui

// SetClipboardText is a no-op on non-Windows platforms.
func SetClipboardText(text string) error {
	return nil
}

// GetClipboardText is a no-op on non-Windows platforms.
func GetClipboardText() string {
	return ""
}
