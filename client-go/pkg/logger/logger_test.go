package logger

import (
	"bytes"
	"errors"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
	"unicode/utf8"
)

type brokenWriter struct{}

func (b *brokenWriter) Write(p []byte) (n int, err error) {
	return 0, errors.New("ERROR_INVALID_HANDLE: the handle is invalid")
}

func TestFormatEntry(t *testing.T) {
	fixedTime := time.Date(2026, 11, 9, 15, 30, 45, 0, time.UTC)
	expectedTs := "[2026-11-09 15:30:45]"

	// Case 1: Already has [TAG]
	entry1 := FormatEntry([]byte("[БОБР] Соединение установлено"), fixedTime)
	expected1 := expectedTs + " [БОБР] Соединение установлено\r\n"
	if string(entry1) != expected1 {
		t.Errorf("FormatEntry([БОБР] ...) = %q; want %q", string(entry1), expected1)
	}

	// Case 2: No tag provided -> defaults to [БОБР]
	entry2 := FormatEntry([]byte("Проверка канала"), fixedTime)
	expected2 := expectedTs + " [БОБР] Проверка канала\r\n"
	if string(entry2) != expected2 {
		t.Errorf("FormatEntry(no tag) = %q; want %q", string(entry2), expected2)
	}

	// Case 3: Startup banner -> preserved as clean banner
	banner := "=== BobrDobr VPN v1.2.2 Started [PID: 12345] ==="
	entry3 := FormatEntry([]byte(banner), fixedTime)
	expected3 := banner + "\r\n"
	if string(entry3) != expected3 {
		t.Errorf("FormatEntry(banner) = %q; want %q", string(entry3), expected3)
	}

	// Case 4: Standard Go log format 2026/11/09 15:30:45 [TAG] message
	stdLog := "2026/11/09 15:30:45 [ПЛОТИНА] Трафик активен"
	entry4 := FormatEntry([]byte(stdLog), fixedTime)
	expected4 := expectedTs + " [ПЛОТИНА] Трафик активен\r\n"
	if string(entry4) != expected4 {
		t.Errorf("FormatEntry(stdLog) = %q; want %q", string(entry4), expected4)
	}

	// Case 5: Multiline stack trace
	stackMsg := "[CRASH] Panic occurred:\ngoroutine 1 [running]:\nmain.main()\n\tmain.go:42"
	entry5 := FormatEntry([]byte(stackMsg), fixedTime)
	lines := strings.Split(string(entry5), "\r\n")
	if len(lines) < 4 {
		t.Fatalf("expected multiline entry, got %d lines: %q", len(lines), string(entry5))
	}
	if !strings.HasPrefix(lines[0], expectedTs+" [CRASH] Panic occurred:") {
		t.Errorf("first line mismatch: %q", lines[0])
	}
	if !strings.HasPrefix(lines[1], "    goroutine 1 [running]:") {
		t.Errorf("continuation line not indented: %q", lines[1])
	}
}

func TestSafeLogWriter_BasicAndMirror(t *testing.T) {
	tmpDir := t.TempDir()
	logPath := filepath.Join(tmpDir, "test.log")

	writer, err := NewSafeLogWriter(logPath, 1024*1024)
	if err != nil {
		t.Fatalf("NewSafeLogWriter failed: %v", err)
	}
	defer writer.Close()

	var stdoutBuf bytes.Buffer
	writer.SetStdoutWriter(&stdoutBuf)

	msg := "[ТЕСТ] Запись лога через SafeLogWriter\n"
	n, err := writer.Write([]byte(msg))
	if err != nil {
		t.Fatalf("Write returned error: %v", err)
	}
	if n != len(msg) {
		t.Errorf("Write returned n=%d; want %d", n, len(msg))
	}

	// Verify file content
	data, err := os.ReadFile(logPath)
	if err != nil {
		t.Fatalf("ReadFile failed: %v", err)
	}
	if !strings.Contains(string(data), "[ТЕСТ] Запись лога через SafeLogWriter") {
		t.Errorf("File log does not contain message: %q", string(data))
	}

	// Verify stdout mirror content
	if !strings.Contains(stdoutBuf.String(), "[ТЕСТ] Запись лога через SafeLogWriter") {
		t.Errorf("Stdout mirror does not contain message: %q", stdoutBuf.String())
	}
}

func TestSafeLogWriter_BrokenStdoutDoesNotPreventFileWrite(t *testing.T) {
	tmpDir := t.TempDir()
	logPath := filepath.Join(tmpDir, "test_broken.log")

	writer, err := NewSafeLogWriter(logPath, 1024*1024)
	if err != nil {
		t.Fatalf("NewSafeLogWriter failed: %v", err)
	}
	defer writer.Close()

	// Simulate Windows GUI subsystem where os.Stdout returns ERROR_INVALID_HANDLE
	writer.SetStdoutWriter(&brokenWriter{})

	msg := "[БОБР] Критический лог: должен записаться в файл несмотря на сломанный stdout\n"
	n, err := writer.Write([]byte(msg))
	if err != nil {
		t.Fatalf("Write should NOT fail even if stdout fails, got err: %v", err)
	}
	if n != len(msg) {
		t.Errorf("Write returned n=%d; want %d", n, len(msg))
	}

	// Verify the persistent log file received the data and flushed!
	data, err := os.ReadFile(logPath)
	if err != nil {
		t.Fatalf("ReadFile failed: %v", err)
	}
	if !strings.Contains(string(data), "Критический лог: должен записаться в файл") {
		t.Errorf("File log missing data when stdout is broken: %q", string(data))
	}
}

func TestSetup_LogCreationInSubfolder(t *testing.T) {
	tmpDir := t.TempDir()
	writer, err := Setup(tmpDir, "1.2.2")
	if err != nil {
		t.Fatalf("Setup failed: %v", err)
	}
	defer writer.Close()

	// 1. Verify log file exists in tmpDir/log/bobrdobr.log
	subLog := filepath.Join(tmpDir, "log", "bobrdobr.log")
	data, err := os.ReadFile(subLog)
	if err != nil {
		t.Fatalf("ReadFile(%q) failed: %v", subLog, err)
	}

	if !strings.Contains(string(data), "=== BobrDobr VPN v1.2.2 Started [PID: ") {
		t.Errorf("Log missing startup banner: %q", string(data))
	}

	// 2. Verify no log file exists directly in tmpDir
	parentLog := filepath.Join(tmpDir, "bobrdobr.log")
	if _, err := os.Stat(parentLog); !os.IsNotExist(err) {
		t.Errorf("bobrdobr.log should not exist in parent appDir, but found: %v", err)
	}
}

func TestSetup_PurgesLegacyLogs(t *testing.T) {
	tmpDir := t.TempDir()

	// Create legacy log files in parent appDir
	legacyLog := filepath.Join(tmpDir, "bobrdobr.log")
	legacyOld := filepath.Join(tmpDir, "bobrdobr.log.old")
	legacyRot := filepath.Join(tmpDir, "bobrdobr-2026.log")

	if err := os.WriteFile(legacyLog, []byte("[БОБР] Старый активный лог\r\n"), 0644); err != nil {
		t.Fatalf("Failed to create legacyLog: %v", err)
	}
	if err := os.WriteFile(legacyOld, []byte("[БОБР] Старый ротированный лог .old\r\n"), 0644); err != nil {
		t.Fatalf("Failed to create legacyOld: %v", err)
	}
	if err := os.WriteFile(legacyRot, []byte("[БОБР] Старый архивный лог\r\n"), 0644); err != nil {
		t.Fatalf("Failed to create legacyRot: %v", err)
	}

	// Also create a leftover migrated log in log/ to verify cleanup
	logDir := filepath.Join(tmpDir, "log")
	if err := os.MkdirAll(logDir, 0755); err != nil {
		t.Fatalf("MkdirAll failed: %v", err)
	}
	leftoverMigrated := filepath.Join(logDir, "bobrdobr-migrated-2026-11-01-120000.log")
	if err := os.WriteFile(leftoverMigrated, []byte("leftover migrated log\r\n"), 0644); err != nil {
		t.Fatalf("Failed to create leftoverMigrated: %v", err)
	}

	// Run Setup which triggers purge
	writer, err := Setup(tmpDir, "1.2.2")
	if err != nil {
		t.Fatalf("Setup failed: %v", err)
	}
	defer writer.Close()

	// Verify all legacy files in appDir are completely removed (os.IsNotExist)
	if _, err := os.Stat(legacyLog); !os.IsNotExist(err) {
		t.Errorf("legacy bobrdobr.log was not removed from parent dir: %v", err)
	}
	if _, err := os.Stat(legacyOld); !os.IsNotExist(err) {
		t.Errorf("legacy bobrdobr.log.old was not removed from parent dir: %v", err)
	}
	if _, err := os.Stat(legacyRot); !os.IsNotExist(err) {
		t.Errorf("legacy bobrdobr-2026.log was not removed from parent dir: %v", err)
	}

	// Verify they were NOT moved into log/
	destOld := filepath.Join(logDir, "bobrdobr.log.old")
	if _, err := os.Stat(destOld); !os.IsNotExist(err) {
		t.Errorf("bobrdobr.log.old should NOT have been moved into log/")
	}
	destRot := filepath.Join(logDir, "bobrdobr-2026.log")
	if _, err := os.Stat(destRot); !os.IsNotExist(err) {
		t.Errorf("bobrdobr-2026.log should NOT have been moved into log/")
	}
	if _, err := os.Stat(leftoverMigrated); !os.IsNotExist(err) {
		t.Errorf("leftover migrated log should have been purged from log/")
	}

	// Verify only log/bobrdobr.log is active
	destActive := filepath.Join(logDir, "bobrdobr.log")
	activeData, err := os.ReadFile(destActive)
	if err != nil {
		t.Fatalf("ReadFile(destActive) failed: %v", err)
	}
	if strings.Contains(string(activeData), "Старый активный лог") {
		t.Errorf("Active log should NOT contain old migrated content: %q", string(activeData))
	}
	if !strings.Contains(string(activeData), "=== BobrDobr VPN v1.2.2 Started [PID: ") {
		t.Errorf("Active log missing startup banner: %q", string(activeData))
	}
}

func TestSafeLogWriter_RotationTimestampedArchive(t *testing.T) {
	tmpDir := t.TempDir()
	logDir := filepath.Join(tmpDir, "log")
	logPath := filepath.Join(logDir, "bobrdobr.log")

	// Set small maxSize to trigger rotation quickly
	maxSize := int64(200)
	writer, err := NewSafeLogWriter(logPath, maxSize)
	if err != nil {
		t.Fatalf("NewSafeLogWriter failed: %v", err)
	}
	defer writer.Close()

	// Write entries exceeding maxSize
	for i := 0; i < 12; i++ {
		msg := fmt.Sprintf("[БОБР] Строка сообщения номер %d для проверки ротации\n", i)
		_, err := writer.Write([]byte(msg))
		if err != nil {
			t.Fatalf("Write #%d failed: %v", i, err)
		}
	}

	// Read log directory entries
	entries, err := os.ReadDir(logDir)
	if err != nil {
		t.Fatalf("ReadDir failed: %v", err)
	}

	var archiveCount int
	var foundTimestamped bool
	for _, e := range entries {
		name := e.Name()
		if name == "bobrdobr.log" {
			continue
		}
		if strings.HasPrefix(name, "bobrdobr-") && strings.HasSuffix(name, ".log") {
			archiveCount++
			foundTimestamped = true

			// Verify archive file contains actual data
			archData, err := os.ReadFile(filepath.Join(logDir, name))
			if err != nil {
				t.Errorf("Failed to read archive %s: %v", name, err)
			}
			if len(archData) == 0 {
				t.Errorf("Archive %s is empty", name)
			}
		}
	}

	if !foundTimestamped || archiveCount == 0 {
		t.Fatalf("Expected at least one timestamped archive bobrdobr-*.log, found %d", archiveCount)
	}

	// Verify active log file still exists and contains current entries
	activeData, err := os.ReadFile(logPath)
	if err != nil {
		t.Fatalf("ReadFile active failed: %v", err)
	}
	if len(activeData) == 0 {
		t.Errorf("Active log file is empty")
	}
}

func TestCleanOldLogs_MaxBackups(t *testing.T) {
	tmpDir := t.TempDir()
	logDir := filepath.Join(tmpDir, "log")
	if err := os.MkdirAll(logDir, 0755); err != nil {
		t.Fatalf("MkdirAll failed: %v", err)
	}

	// Active log file
	activePath := filepath.Join(logDir, "bobrdobr.log")
	_ = os.WriteFile(activePath, []byte("active"), 0644)

	// Create 10 rotated log files with distinct chronological dates
	for i := 1; i <= 10; i++ {
		name := fmt.Sprintf("bobrdobr-2026-11-%02d-120000.log", i)
		path := filepath.Join(logDir, name)
		_ = os.WriteFile(path, []byte(fmt.Sprintf("archive %d", i)), 0644)
	}

	// Retention: max 4 backups, maxAgeDays 0 (disabled age check)
	maxBackups := 4
	if err := CleanOldLogs(logDir, maxBackups, 0); err != nil {
		t.Fatalf("CleanOldLogs failed: %v", err)
	}

	entries, err := os.ReadDir(logDir)
	if err != nil {
		t.Fatalf("ReadDir failed: %v", err)
	}

	var remainingArchives []string
	for _, e := range entries {
		name := e.Name()
		if name == "bobrdobr.log" {
			continue
		}
		remainingArchives = append(remainingArchives, name)
	}

	if len(remainingArchives) != maxBackups {
		t.Fatalf("Expected %d archives remaining, got %d: %v", maxBackups, len(remainingArchives), remainingArchives)
	}

	// The newest 4 archives must be 07, 08, 09, 10
	expectedNewest := []string{
		"bobrdobr-2026-11-07-120000.log",
		"bobrdobr-2026-11-08-120000.log",
		"bobrdobr-2026-11-09-120000.log",
		"bobrdobr-2026-11-10-120000.log",
	}

	for _, exp := range expectedNewest {
		p := filepath.Join(logDir, exp)
		if _, err := os.Stat(p); os.IsNotExist(err) {
			t.Errorf("Expected newest archive %s to be preserved, but it was deleted", exp)
		}
	}

	// Oldest ones (01 to 06) must be deleted
	for i := 1; i <= 6; i++ {
		oldName := fmt.Sprintf("bobrdobr-2026-11-%02d-120000.log", i)
		p := filepath.Join(logDir, oldName)
		if _, err := os.Stat(p); !os.IsNotExist(err) {
			t.Errorf("Expected older archive %s to be purged, but it still exists", oldName)
		}
	}

	// Active log file must NOT be deleted
	if _, err := os.Stat(activePath); os.IsNotExist(err) {
		t.Errorf("Active bobrdobr.log was deleted by CleanOldLogs")
	}
}

func TestCleanOldLogs_MaxAgeDays(t *testing.T) {
	tmpDir := t.TempDir()
	logDir := filepath.Join(tmpDir, "log")
	if err := os.MkdirAll(logDir, 0755); err != nil {
		t.Fatalf("MkdirAll failed: %v", err)
	}

	// Active log
	activePath := filepath.Join(logDir, "bobrdobr.log")
	_ = os.WriteFile(activePath, []byte("active"), 0644)

	// Old archive with date from 20 days ago in filename
	oldTimestamp := time.Now().Add(-20 * 24 * time.Hour).Format("2006-01-02-150405")
	expiredArchive := filepath.Join(logDir, fmt.Sprintf("bobrdobr-%s.log", oldTimestamp))
	_ = os.WriteFile(expiredArchive, []byte("expired archive"), 0644)

	// Old legacy .old file with mtime set to 25 days ago
	expiredOld := filepath.Join(logDir, "bobrdobr.log.old")
	_ = os.WriteFile(expiredOld, []byte("expired old file"), 0644)
	twentyFiveDaysAgo := time.Now().Add(-25 * 24 * time.Hour)
	_ = os.Chtimes(expiredOld, twentyFiveDaysAgo, twentyFiveDaysAgo)

	// Fresh archive (1 hour old)
	recentTimestamp := time.Now().Add(-1 * time.Hour).Format("2006-01-02-150405")
	freshArchive := filepath.Join(logDir, fmt.Sprintf("bobrdobr-%s.log", recentTimestamp))
	_ = os.WriteFile(freshArchive, []byte("fresh archive"), 0644)

	// Run CleanOldLogs with maxAgeDays = 14
	if err := CleanOldLogs(logDir, 10, 14); err != nil {
		t.Fatalf("CleanOldLogs failed: %v", err)
	}

	// Verify expiredArchive is deleted
	if _, err := os.Stat(expiredArchive); !os.IsNotExist(err) {
		t.Errorf("expiredArchive %s should have been deleted by maxAgeDays", expiredArchive)
	}

	// Verify expiredOld is deleted
	if _, err := os.Stat(expiredOld); !os.IsNotExist(err) {
		t.Errorf("expiredOld %s should have been deleted by maxAgeDays", expiredOld)
	}

	// Verify freshArchive is kept
	if _, err := os.Stat(freshArchive); os.IsNotExist(err) {
		t.Errorf("freshArchive %s should have been kept", freshArchive)
	}

	// Verify active log is kept
	if _, err := os.Stat(activePath); os.IsNotExist(err) {
		t.Errorf("Active bobrdobr.log should have been kept")
	}
}

func TestSafeLogWriter_PruningOnRotation(t *testing.T) {
	tmpDir := t.TempDir()
	logDir := filepath.Join(tmpDir, "log")
	logPath := filepath.Join(logDir, "bobrdobr.log")

	writer, err := NewSafeLogWriter(logPath, 150)
	if err != nil {
		t.Fatalf("NewSafeLogWriter failed: %v", err)
	}
	defer writer.Close()

	// Configure retention: max 2 backups
	writer.SetRetention(2, 14)

	// Write enough to trigger multiple rotations
	for i := 0; i < 20; i++ {
		_, err := writer.Write([]byte(fmt.Sprintf("[БОБР] Сообщение %d для переполнения и ротации\n", i)))
		if err != nil {
			t.Fatalf("Write %d failed: %v", i, err)
		}
	}

	// Check number of rotated archive files in logDir
	entries, err := os.ReadDir(logDir)
	if err != nil {
		t.Fatalf("ReadDir failed: %v", err)
	}

	var archiveCount int
	for _, e := range entries {
		name := e.Name()
		if name == "bobrdobr.log" {
			continue
		}
		if strings.HasPrefix(name, "bobrdobr-") && strings.HasSuffix(name, ".log") {
			archiveCount++
		}
	}

	if archiveCount > 2 {
		t.Errorf("Expected at most 2 rotated archive files after pruning on rotation, got %d", archiveCount)
	}
}

func TestSetup_WritesBannerAndCapturesStandardLog(t *testing.T) {
	tmpDir := t.TempDir()
	writer, err := Setup(tmpDir, "1.2.2")
	if err != nil {
		t.Fatalf("Setup failed: %v", err)
	}
	defer writer.Close()

	log.Println("[БОБР] Стандартный лог через log.Println")

	logPath := filepath.Join(tmpDir, "log", "bobrdobr.log")
	data, err := os.ReadFile(logPath)
	if err != nil {
		t.Fatalf("ReadFile failed: %v", err)
	}

	content := string(data)
	if !strings.Contains(content, "=== BobrDobr VPN v1.2.2 Started [PID: ") {
		t.Errorf("Log missing startup banner: %q", content)
	}
	if !strings.Contains(content, "[БОБР] Стандартный лог через log.Println") {
		t.Errorf("Log missing message from log.Println: %q", content)
	}
}

func TestSafeLogWriter_UTF8BOM_NewAndEmptyFiles(t *testing.T) {
	tmpDir := t.TempDir()

	// 1. Newly created log file must start with UTF-8 BOM immediately upon creation
	logPath1 := filepath.Join(tmpDir, "new.log")
	writer1, err := NewSafeLogWriter(logPath1, 1024*1024)
	if err != nil {
		t.Fatalf("NewSafeLogWriter failed: %v", err)
	}
	defer writer1.Close()

	data1, err := os.ReadFile(logPath1)
	if err != nil {
		t.Fatalf("ReadFile failed: %v", err)
	}
	if !bytes.Equal(data1, UTF8BOM) {
		t.Fatalf("Newly created log file must contain exactly UTF-8 BOM, got %v", data1)
	}

	// 2. Writing Russian text to new file retains UTF-8 BOM and valid UTF-8
	msg := "[БОБР] Проверка записи UTF-8 с BOM\n"
	_, err = writer1.Write([]byte(msg))
	if err != nil {
		t.Fatalf("Write failed: %v", err)
	}

	data1After, err := os.ReadFile(logPath1)
	if err != nil {
		t.Fatalf("ReadFile after write failed: %v", err)
	}
	if !bytes.HasPrefix(data1After, UTF8BOM) {
		t.Errorf("Log file lost UTF-8 BOM after write: %v", data1After[:min(len(data1After), 10)])
	}
	if !utf8.Valid(data1After) {
		t.Errorf("Log file content is not valid UTF-8: %q", string(data1After))
	}
	if !strings.Contains(string(data1After), "Проверка записи UTF-8 с BOM") {
		t.Errorf("Log file missing written text: %q", string(data1After))
	}

	// 3. Existing empty file (size == 0) must also be initialized with UTF-8 BOM
	logPath2 := filepath.Join(tmpDir, "empty.log")
	if err := os.WriteFile(logPath2, []byte{}, 0644); err != nil {
		t.Fatalf("WriteFile failed: %v", err)
	}

	writer2, err := NewSafeLogWriter(logPath2, 1024*1024)
	if err != nil {
		t.Fatalf("NewSafeLogWriter on empty file failed: %v", err)
	}
	defer writer2.Close()

	data2, err := os.ReadFile(logPath2)
	if err != nil {
		t.Fatalf("ReadFile on empty file failed: %v", err)
	}
	if !bytes.Equal(data2, UTF8BOM) {
		t.Errorf("Pre-existing empty log file was not seeded with UTF-8 BOM, got %v", data2)
	}
}

func TestSafeLogWriter_UTF8BOM_RotatedArchives(t *testing.T) {
	tmpDir := t.TempDir()
	logPath := filepath.Join(tmpDir, "bobrdobr.log")

	// Trigger rotation with small maxSize
	writer, err := NewSafeLogWriter(logPath, 150)
	if err != nil {
		t.Fatalf("NewSafeLogWriter failed: %v", err)
	}
	defer writer.Close()

	for i := 0; i < 15; i++ {
		_, err := writer.Write([]byte(fmt.Sprintf("[БОБР] Запись ротации #%d с русским текстом\n", i)))
		if err != nil {
			t.Fatalf("Write %d failed: %v", i, err)
		}
	}

	// Verify active log file starts with UTF-8 BOM
	activeData, err := os.ReadFile(logPath)
	if err != nil {
		t.Fatalf("ReadFile active failed: %v", err)
	}
	if !bytes.HasPrefix(activeData, UTF8BOM) {
		t.Errorf("Active log file after rotation does not start with UTF-8 BOM")
	}
	if !utf8.Valid(activeData) {
		t.Errorf("Active log file is not valid UTF-8")
	}

	// Verify all rotated archive files also start with UTF-8 BOM and have valid UTF-8
	entries, err := os.ReadDir(tmpDir)
	if err != nil {
		t.Fatalf("ReadDir failed: %v", err)
	}

	var archiveCount int
	for _, e := range entries {
		name := e.Name()
		if name == "bobrdobr.log" {
			continue
		}
		if strings.HasPrefix(name, "bobrdobr-") && strings.HasSuffix(name, ".log") {
			archiveCount++
			archData, err := os.ReadFile(filepath.Join(tmpDir, name))
			if err != nil {
				t.Fatalf("ReadFile archive %s failed: %v", name, err)
			}
			if !bytes.HasPrefix(archData, UTF8BOM) {
				t.Errorf("Archive %s does not start with UTF-8 BOM", name)
			}
			if !utf8.Valid(archData) {
				t.Errorf("Archive %s is not valid UTF-8", name)
			}
		}
	}

	if archiveCount == 0 {
		t.Fatalf("Expected at least one rotated archive")
	}
}

func TestFormatEntry_UTF8Sanitization(t *testing.T) {
	fixedTime := time.Date(2026, 11, 9, 20, 0, 0, 0, time.UTC)

	// 1. Invalid UTF-8 byte sequences must be sanitized to valid UTF-8
	invalidBytes := []byte("[БОБР] Ошибка \xff\xfe тест \x80\x81")
	formattedInvalid := FormatEntry(invalidBytes, fixedTime)
	if !utf8.Valid(formattedInvalid) {
		t.Fatalf("FormatEntry result is not valid UTF-8: %v", formattedInvalid)
	}
	// Invalid sequences should be stripped
	strFormatted := string(formattedInvalid)
	if strings.Contains(strFormatted, "\xff") || strings.Contains(strFormatted, "\xfe") {
		t.Errorf("FormatEntry did not sanitize invalid bytes: %q", strFormatted)
	}
	if !strings.Contains(strFormatted, "Ошибка") || !strings.Contains(strFormatted, "тест") {
		t.Errorf("FormatEntry stripped valid Russian text: %q", strFormatted)
	}

	// 2. Valid UTF-8 emojis and Russian text must be perfectly preserved
	validMsg := "[ПЛОТИНА] 🟢 БобрДобр VPN — Защищено: Сервер Франкфурт [WireGuard]"
	formattedValid := FormatEntry([]byte(validMsg), fixedTime)
	if !utf8.Valid(formattedValid) {
		t.Fatalf("FormatEntry valid result is not valid UTF-8: %v", formattedValid)
	}
	if !strings.Contains(string(formattedValid), "🟢 БобрДобр VPN — Защищено") {
		t.Errorf("FormatEntry corrupted valid emoji or text: %q", string(formattedValid))
	}

	// 3. Startup banner with invalid bytes
	bannerWithInvalid := []byte("=== Startup \xff\xfe Banner ===")
	formattedBanner := FormatEntry(bannerWithInvalid, fixedTime)
	if !utf8.Valid(formattedBanner) {
		t.Fatalf("FormatEntry banner is not valid UTF-8: %v", formattedBanner)
	}
	if !strings.Contains(string(formattedBanner), "=== Startup  Banner ===") {
		t.Errorf("FormatEntry banner mismatch: %q", string(formattedBanner))
	}
}
