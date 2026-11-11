//go:build windows

package main

import (
	"fmt"
	"log"
	"os"
	"path/filepath"
	"unsafe"

	"golang.org/x/sys/windows"
	"golang.org/x/sys/windows/registry"
)

var (
	modShell32                                  = windows.NewLazySystemDLL("shell32.dll")
	procSetCurrentProcessExplicitAppUserModelID = modShell32.NewProc("SetCurrentProcessExplicitAppUserModelID")
)

// SetCurrentProcessExplicitAppUserModelID assigns an explicit Application User Model ID (AUMID)
// to the current process so Windows 10/11 Action Center associates notifications with "БобрДобр VPN".
func SetCurrentProcessExplicitAppUserModelID(aumid string) {
	ptr, err := windows.UTF16PtrFromString(aumid)
	if err != nil {
		return
	}
	r1, _, _ := procSetCurrentProcessExplicitAppUserModelID.Call(uintptr(unsafe.Pointer(ptr)))
	if r1 != 0 {
		log.Printf("[AUMID] SetCurrentProcessExplicitAppUserModelID(%s) returned 0x%x", aumid, r1)
	} else {
		log.Printf("[AUMID] Установлен идентификатор процесса: %s", aumid)
	}
}

// ensureAppUserModelIDRegistry registers the AUMID in Windows Registry under HKCU\Software\Classes\AppUserModelId\BobrDobr.VPN.Client
// so the Windows Notification Manager displays "БобрДобр VPN" as the notification source title instead of "BobrDobr.exe".
func ensureAppUserModelIDRegistry() {
	const aumidKey = `Software\Classes\AppUserModelId\BobrDobr.VPN.Client`

	k, _, err := registry.CreateKey(registry.CURRENT_USER, aumidKey, registry.SET_VALUE|registry.QUERY_VALUE)
	if err != nil {
		log.Printf("[AUMID] Ошибка открытия/создания ключа реестра %s: %v", aumidKey, err)
		return
	}
	defer k.Close()

	if err := k.SetStringValue("DisplayName", "БобрДобр VPN"); err != nil {
		log.Printf("[AUMID] Ошибка записи DisplayName: %v", err)
	}

	icoPath := findBobrLogoIcoPath()
	if icoPath != "" {
		if err := k.SetStringValue("IconUri", icoPath); err != nil {
			log.Printf("[AUMID] Ошибка записи IconUri: %v", err)
		}
	}

	if err := k.SetStringValue("IconBackgroundColor", "0"); err != nil {
		log.Printf("[AUMID] Ошибка записи IconBackgroundColor: %v", err)
	}

	registerBobrDobrProtocol()
}

// registerBobrDobrProtocol registers the custom URL protocol bobrdobr:// in HKCU\Software\Classes\bobrdobr
// so Windows Action Center interactive notifications can invoke actions back into the application.
func registerBobrDobrProtocol() {
	exePath, err := os.Executable()
	if err != nil || exePath == "" {
		return
	}

	const protoKey = `Software\Classes\bobrdobr`
	k, _, err := registry.CreateKey(registry.CURRENT_USER, protoKey, registry.SET_VALUE)
	if err != nil {
		log.Printf("[ПРОТОКОЛ] Ошибка создания ключа %s: %v", protoKey, err)
		return
	}
	defer k.Close()

	if err := k.SetStringValue("", "URL:BobrDobr Protocol"); err != nil {
		log.Printf("[ПРОТОКОЛ] Ошибка записи (Default): %v", err)
	}
	if err := k.SetStringValue("URL Protocol", ""); err != nil {
		log.Printf("[ПРОТОКОЛ] Ошибка записи URL Protocol: %v", err)
	}

	cmdKey, _, err := registry.CreateKey(registry.CURRENT_USER, protoKey+`\shell\open\command`, registry.SET_VALUE)
	if err != nil {
		log.Printf("[ПРОТОКОЛ] Ошибка создания ключа shell\\open\\command: %v", err)
		return
	}
	defer cmdKey.Close()

	cmdVal := fmt.Sprintf(`"%s" "%%1"`, exePath)
	if err := cmdKey.SetStringValue("", cmdVal); err != nil {
		log.Printf("[ПРОТОКОЛ] Ошибка записи command: %v", err)
	} else {
		log.Printf("[ПРОТОКОЛ] Протокол bobrdobr:// зарегистрирован: %s", cmdVal)
	}
}

// findBobrLogoIcoPath locates the bobr_logo.ico file on the system
func findBobrLogoIcoPath() string {
	exePath, err := os.Executable()
	if err == nil {
		exeDir := filepath.Dir(exePath)
		candidates := []string{
			filepath.Join(exeDir, "assets", "bobr_logo.ico"),
			filepath.Join(exeDir, "bobr_logo.ico"),
			filepath.Join(exeDir, "..", "assets", "bobr_logo.ico"),
			filepath.Join(exeDir, "..", "..", "assets", "bobr_logo.ico"),
		}
		for _, c := range candidates {
			if _, err := os.Stat(c); err == nil {
				if abs, err := filepath.Abs(c); err == nil {
					return abs
				}
				return c
			}
		}
	}

	progFiles := os.Getenv("ProgramFiles")
	if progFiles == "" {
		progFiles = `C:\Program Files`
	}
	installedIco := filepath.Join(progFiles, "BobrDobr", "assets", "bobr_logo.ico")
	if _, err := os.Stat(installedIco); err == nil {
		return installedIco
	}

	appData := os.Getenv("LOCALAPPDATA")
	if appData != "" {
		localIco := filepath.Join(appData, "Programs", "BobrDobr", "assets", "bobr_logo.ico")
		if _, err := os.Stat(localIco); err == nil {
			return localIco
		}
	}

	if exePath != "" {
		return filepath.Join(filepath.Dir(exePath), "assets", "bobr_logo.ico")
	}
	return `C:\Program Files\BobrDobr\assets\bobr_logo.ico`
}

// allowSetForegroundWindow grants foreground window activation permission to any process.
func allowSetForegroundWindow() {
	u32 := windows.NewLazySystemDLL("user32.dll")
	pAllow := u32.NewProc("AllowSetForegroundWindow")
	if pAllow.Find() == nil {
		_, _, _ = pAllow.Call(uintptr(0xFFFFFFFF)) // ASFW_ANY
	}
}
