//go:build windows

package tray

import (
	"encoding/base64"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"syscall"

	"golang.org/x/sys/windows"
)

// findIconPath searches for bobr_logo.ico in candidate locations.
func findIconPath() string {
	exePath, _ := os.Executable()
	exeDir := filepath.Dir(exePath)

	progFiles := os.Getenv("ProgramFiles")
	if progFiles == "" {
		progFiles = `C:\Program Files`
	}
	localAppData := os.Getenv("LOCALAPPDATA")

	candidates := []string{
		"assets/bobr_logo.ico",
		filepath.Join("assets", "bobr_logo.ico"),
		filepath.Join("..", "assets", "bobr_logo.ico"),
		filepath.Join(exeDir, "assets", "bobr_logo.ico"),
		filepath.Join(exeDir, "bobr_logo.ico"),
		filepath.Join(exeDir, "..", "assets", "bobr_logo.ico"),
		filepath.Join(progFiles, "BobrDobr", "assets", "bobr_logo.ico"),
		filepath.Join(progFiles, "BobrDobr", "bobr_logo.ico"),
	}
	if localAppData != "" {
		candidates = append(candidates,
			filepath.Join(localAppData, "Programs", "BobrDobr", "assets", "bobr_logo.ico"),
			filepath.Join(localAppData, "Programs", "BobrDobr", "bobr_logo.ico"),
		)
	}

	for _, c := range candidates {
		if fi, err := os.Stat(c); err == nil && !fi.IsDir() {
			if abs, err := filepath.Abs(c); err == nil {
				return abs
			}
			return c
		}
	}
	return ""
}

// ShowToastWithAction displays an interactive Windows WinRT toast notification with an action button.
// Clicking the action button triggers protocol activation (e.g. bobrdobr://action/disable-notifications).
// It executes in a separate background goroutine and never blocks the caller.
func ShowToastWithAction(aumid, title, message, buttonText, protocolArg string) error {
	// Pass empty iconPath: Windows already renders the crisp application logo in the toast header.
	// Omitting appLogoOverride prevents scaling low-res icon frames into a blurry avatar.
	rawXml := buildToastXml(title, message, buttonText, protocolArg, "")

	b64Xml := base64.StdEncoding.EncodeToString([]byte(rawXml))

	script := fmt.Sprintf(`[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null; [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null; $xml = New-Object Windows.Data.Xml.Dom.XmlDocument; $xml.LoadXml([System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('%s'))); $toast = New-Object Windows.UI.Notifications.ToastNotification($xml); [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('%s').Show($toast)`, b64Xml, aumid)

	go func() {
		cmd := exec.Command("powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script)
		cmd.SysProcAttr = &syscall.SysProcAttr{
			HideWindow:    true,
			CreationFlags: windows.CREATE_NO_WINDOW,
		}
		_ = cmd.Run()
	}()

	return nil
}
