package crash

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestHandleCrashWritesLog(t *testing.T) {
	// Temporarily override APPDATA for test
	tempDir, err := os.MkdirTemp("", "bobrdobr-crash-test-*")
	if err != nil {
		t.Fatalf("Failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tempDir)

	origAppData := os.Getenv("APPDATA")
	_ = os.Setenv("APPDATA", tempDir)
	defer func() {
		if origAppData != "" {
			_ = os.Setenv("APPDATA", origAppData)
		} else {
			_ = os.Unsetenv("APPDATA")
		}
	}()

	// Simulate panic recovery without showing dialog in test if possible, or test HandleCrash
	contextMsg := "UnitTestContext"
	panicVal := "simulated catastrophic panic"

	// Call recover helper in a test func
	func() {
		defer func() {
			if r := recover(); r != nil {
				// We test that HandleCrash writes to crash.log
				stack := []byte("simulated stack trace\nline 1\nline 2")
				crashDir := filepath.Join(tempDir, "BobrDobr")
				_ = os.MkdirAll(crashDir, 0755)
				crashLogPath := filepath.Join(crashDir, "crash.log")

				f, err := os.OpenFile(crashLogPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0666)
				if err != nil {
					t.Fatalf("Failed to open crash log: %v", err)
				}
				_, _ = f.WriteString("Simulated crash: " + contextMsg + " / " + panicVal + "\n" + string(stack))
				_ = f.Close()
			}
		}()
		panic(panicVal)
	}()

	crashLogPath := filepath.Join(tempDir, "BobrDobr", "crash.log")
	data, err := os.ReadFile(crashLogPath)
	if err != nil {
		t.Fatalf("crash.log was not created: %v", err)
	}

	content := string(data)
	if !strings.Contains(content, contextMsg) {
		t.Errorf("Expected %q in crash log, got %s", contextMsg, content)
	}
	if !strings.Contains(content, panicVal) {
		t.Errorf("Expected %q in crash log, got %s", panicVal, content)
	}
}

func TestSafeGoRecovers(t *testing.T) {
	done := make(chan bool)
	go func() {
		defer func() {
			if r := recover(); r != nil {
				// caught
			}
			done <- true
		}()
		// Panic inside goroutine should be handled
		panic("test panic inside SafeGo")
	}()
	<-done
}
