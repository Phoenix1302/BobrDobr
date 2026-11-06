//go:build !windows

package crash

import (
	"fmt"
	"log"
	"os"
	"path/filepath"
	"runtime/debug"
	"sync"
	"time"
)

var crashMu sync.Mutex

// HandleCrash writes crash logs to user config directory and logs to stderr.
func HandleCrash(r interface{}, contextMsg string) {
	if r == nil {
		return
	}

	crashMu.Lock()
	defer crashMu.Unlock()

	stack := debug.Stack()
	home, _ := os.UserHomeDir()
	crashDir := filepath.Join(home, ".config", "BobrDobr")
	_ = os.MkdirAll(crashDir, 0755)
	crashLogPath := filepath.Join(crashDir, "crash.log")

	timestamp := time.Now().Format("2006-01-02 15:04:05")
	entry := fmt.Sprintf(
		"================================================================================\n"+
			"[FATAL CRASH] %s\n"+
			"Context: %s\n"+
			"Error / Panic: %v\n\n"+
			"Stack Trace:\n%s\n"+
			"================================================================================\n\n",
		timestamp, contextMsg, r, string(stack),
	)

	if f, err := os.OpenFile(crashLogPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0666); err == nil {
		_, _ = f.WriteString(entry)
		_ = f.Close()
	}

	log.Printf("[CRASH] %s: %v\n%s", contextMsg, r, string(stack))
}

// ShowCrashDialog is a stub on non-Windows platforms.
func ShowCrashDialog(contextMsg string, r interface{}, crashLogPath string) {}

// Recover catches any panic, writes crash logs, and logs the incident.
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
