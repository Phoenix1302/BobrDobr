//go:build windows

package crash

import (
	"fmt"
	"log"
	"os"
	"path/filepath"
	"runtime/debug"
	"sync"
	"time"
	"unsafe"

	"golang.org/x/sys/windows"
)

var (
	moduser32       = windows.NewLazySystemDLL("user32.dll")
	procMessageBoxW = moduser32.NewProc("MessageBoxW")
	crashMu         sync.Mutex
)

const (
	MB_OK          = 0x00000000
	MB_ICONERROR   = 0x00000010
	MB_SYSTEMMODAL = 0x00001000
	MB_TASKMODAL   = 0x00002000
)

// HandleCrash writes crash logs with timestamp, error message, and debug.Stack()
// to %APPDATA%\BobrDobr\crash.log and displays a native Win32 MessageBoxW modal.
func HandleCrash(r interface{}, contextMsg string) {
	if r == nil {
		return
	}

	crashMu.Lock()
	defer crashMu.Unlock()

	stack := debug.Stack()

	// 1. Resolve %APPDATA%\BobrDobr\crash.log
	appData := os.Getenv("APPDATA")
	if appData == "" {
		home, _ := os.UserHomeDir()
		appData = filepath.Join(home, "AppData", "Roaming")
	}
	crashDir := filepath.Join(appData, "BobrDobr")
	_ = os.MkdirAll(crashDir, 0755)
	crashLogPath := filepath.Join(crashDir, "crash.log")

	timestamp := time.Now().Format("2006-01-02 15:04:05")
	entry := fmt.Sprintf(
		"================================================================================\r\n"+
			"[FATAL CRASH] %s\r\n"+
			"Context: %s\r\n"+
			"Error / Panic: %v\r\n\r\n"+
			"Stack Trace:\r\n%s\r\n"+
			"================================================================================\r\n\r\n",
		timestamp, contextMsg, r, string(stack),
	)

	// Write crash entry to file
	if f, err := os.OpenFile(crashLogPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0666); err == nil {
		_, _ = f.WriteString(entry)
		_ = f.Close()
	}

	// Output to standard logging
	log.Printf("[CRASH] %s: %v\n%s", contextMsg, r, string(stack))

	// 2. Display native Windows MessageBoxW so crashes are visible to the user
	ShowCrashDialog(contextMsg, r, crashLogPath)
}

// ShowCrashDialog displays a native Windows MessageBoxW dialog with MB_ICONERROR | MB_OK.
func ShowCrashDialog(contextMsg string, r interface{}, crashLogPath string) {
	titlePtr, _ := windows.UTF16PtrFromString("BobrDobr VPN - Критическая ошибка")
	msg := fmt.Sprintf(
		"В приложении BobrDobr VPN произошла критическая ошибка.\n\n"+
			"Контекст: %s\n"+
			"Ошибка: %v\n\n"+
			"Подробный стек вызовов сохранен в:\n%s",
		contextMsg, r, crashLogPath,
	)
	textPtr, _ := windows.UTF16PtrFromString(msg)
	procMessageBoxW.Call(
		0,
		uintptr(unsafe.Pointer(textPtr)),
		uintptr(unsafe.Pointer(titlePtr)),
		uintptr(MB_OK|MB_ICONERROR|MB_TASKMODAL),
	)
}

// Recover catches any panic, writes crash logs, and displays the crash dialog.
func Recover(contextMsg string) {
	if r := recover(); r != nil {
		HandleCrash(r, contextMsg)
	}
}

// SafeGo executes a goroutine wrapped in panic recovery.
func SafeGo(contextMsg string, fn func()) {
	go func() {
		defer func() {
			if r := recover(); r != nil {
				HandleCrash(r, contextMsg)
			}
		}()
		fn()
	}()
}
