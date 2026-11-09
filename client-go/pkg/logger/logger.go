package logger

import (
	"errors"
	"fmt"
	"io"
	"log"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"
)

// DefaultMaxLogSize is 5 MB before log rotation triggers.
const DefaultMaxLogSize int64 = 5 * 1024 * 1024

// DefaultMaxBackups is the maximum number of rotated log archives to retain.
const DefaultMaxBackups int = 7

// DefaultMaxAgeDays is the maximum age in days before a rotated log archive is purged.
const DefaultMaxAgeDays int = 14

// SafeLogWriter safely logs to a persistent file and optionally to stdout.
// Under the Windows GUI Subsystem (-H windowsgui), os.Stdout is an invalid handle (ERROR_INVALID_HANDLE).
// SafeLogWriter guarantees that writes to the persistent log file ALWAYS occur and sync,
// regardless of any errors or missing handles on os.Stdout.
type SafeLogWriter struct {
	mu          sync.Mutex
	logDir      string
	logPath     string
	maxSize     int64
	maxBackups  int
	maxAgeDays  int
	currentSize int64
	file        *os.File
	stdout      io.Writer
}

// NewSafeLogWriter creates and initializes a SafeLogWriter for logPath.
func NewSafeLogWriter(logPath string, maxSize int64) (*SafeLogWriter, error) {
	if maxSize <= 0 {
		maxSize = DefaultMaxLogSize
	}

	dir := filepath.Dir(logPath)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return nil, fmt.Errorf("failed to create log directory: %w", err)
	}

	w := &SafeLogWriter{
		logDir:     dir,
		logPath:    logPath,
		maxSize:    maxSize,
		maxBackups: DefaultMaxBackups,
		maxAgeDays: DefaultMaxAgeDays,
		stdout:     os.Stdout,
	}

	// Prune old rotated logs in the directory on startup
	_ = CleanOldLogsEx(w.logDir, filepath.Base(w.logPath), w.maxBackups, w.maxAgeDays)

	// Check existing file size and rotate if already at or above cap
	if fi, err := os.Stat(logPath); err == nil {
		w.currentSize = fi.Size()
		if w.currentSize >= w.maxSize {
			w.rotateLocked()
		}
	}

	if w.file == nil {
		f, err := os.OpenFile(logPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
		if err != nil {
			return nil, fmt.Errorf("failed to open log file %q: %w", logPath, err)
		}
		w.file = f
	}

	return w, nil
}

// SetStdoutWriter sets the secondary stdout writer (useful for tests or custom redirection).
func (w *SafeLogWriter) SetStdoutWriter(out io.Writer) {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.stdout = out
}

// SetRetention updates the backup count and max age retention parameters and immediately prunes old logs.
func (w *SafeLogWriter) SetRetention(maxBackups int, maxAgeDays int) {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.maxBackups = maxBackups
	w.maxAgeDays = maxAgeDays
	_ = CleanOldLogsEx(w.logDir, filepath.Base(w.logPath), w.maxBackups, w.maxAgeDays)
}

// LogPath returns the active log file path.
func (w *SafeLogWriter) LogPath() string {
	w.mu.Lock()
	defer w.mu.Unlock()
	return w.logPath
}

// LogDir returns the directory containing log files.
func (w *SafeLogWriter) LogDir() string {
	w.mu.Lock()
	defer w.mu.Unlock()
	return w.logDir
}

// CleanOldLogs triggers retention pruning in the writer's log directory.
func (w *SafeLogWriter) CleanOldLogs() error {
	w.mu.Lock()
	defer w.mu.Unlock()
	return CleanOldLogsEx(w.logDir, filepath.Base(w.logPath), w.maxBackups, w.maxAgeDays)
}

// Close flushes and closes the underlying log file handle.
func (w *SafeLogWriter) Close() error {
	w.mu.Lock()
	defer w.mu.Unlock()
	if w.file != nil {
		_ = w.file.Sync()
		err := w.file.Close()
		w.file = nil
		return err
	}
	return nil
}

// rotateLocked rotates logPath to a timestamped archive: bobrdobr-YYYY-MM-DD-HHMMSS.log,
// then opens a clean active log file and prunes old archives.
// Caller MUST hold w.mu.
func (w *SafeLogWriter) rotateLocked() {
	if w.file != nil {
		_ = w.file.Sync()
		_ = w.file.Close()
		w.file = nil
	}

	baseName := strings.TrimSuffix(filepath.Base(w.logPath), filepath.Ext(w.logPath))
	ts := time.Now().Format("2006-01-02-150405")
	archiveName := fmt.Sprintf("%s-%s.log", baseName, ts)
	archivePath := filepath.Join(w.logDir, archiveName)

	// If destination already exists (e.g. multiple rotations within the same second), append a sequence number
	if _, err := os.Stat(archivePath); err == nil {
		for i := 1; ; i++ {
			altName := fmt.Sprintf("%s-%s-%d.log", baseName, ts, i)
			altPath := filepath.Join(w.logDir, altName)
			if _, err := os.Stat(altPath); os.IsNotExist(err) {
				archivePath = altPath
				break
			}
		}
	}

	err := os.Rename(w.logPath, archivePath)
	if err != nil {
		// Fallback move (copy + remove) if rename fails
		if moveErr := moveFile(w.logPath, archivePath); moveErr != nil {
			// Extreme fallback: truncate active file so it never grows unboundedly
			f, truncErr := os.OpenFile(w.logPath, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0644)
			if truncErr == nil {
				w.file = f
				w.currentSize = 0
			}
			return
		}
	}

	// Open a clean new active log file
	f, openErr := os.OpenFile(w.logPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
	if openErr == nil {
		w.file = f
		w.currentSize = 0
	}

	// Run retention pruning on rotated files
	_ = CleanOldLogsEx(w.logDir, filepath.Base(w.logPath), w.maxBackups, w.maxAgeDays)
}

// moveFile attempts to move a file via rename, falling back to copy+delete.
func moveFile(src, dst string) error {
	if err := os.Rename(src, dst); err == nil {
		return nil
	}

	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()

	out, err := os.OpenFile(dst, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0644)
	if err != nil {
		return err
	}

	if _, err := io.Copy(out, in); err != nil {
		_ = out.Close()
		return err
	}

	if err := out.Close(); err != nil {
		return err
	}
	_ = in.Close()

	return os.Remove(src)
}

// parseLogTimestamp parses timestamp from a rotated log filename.
func parseLogTimestamp(name string) (time.Time, error) {
	base := filepath.Base(name)
	ext := filepath.Ext(base)
	for ext != "" {
		base = strings.TrimSuffix(base, ext)
		ext = filepath.Ext(base)
	}

	// If there's an index suffix like -1, -2 at the end, strip it
	if idx := strings.LastIndex(base, "-"); idx != -1 && len(base)-idx <= 4 {
		suffix := base[idx+1:]
		allDigits := len(suffix) > 0
		for _, r := range suffix {
			if r < '0' || r > '9' {
				allDigits = false
				break
			}
		}
		if allDigits {
			base = base[:idx]
		}
	}

	layouts := []string{
		"2006-01-02-150405",
		"20060102-150405",
		"2006-01-02_15-04-05",
		"2006-01-02",
		"20060102",
	}

	// Try parsing full base
	for _, l := range layouts {
		if t, err := time.Parse(l, base); err == nil {
			return t, nil
		}
	}

	// Try stripping prefixes before a dash (e.g. "bobrdobr-", "migrated-", etc.)
	parts := strings.Split(base, "-")
	for i := 1; i < len(parts); i++ {
		candidate := strings.Join(parts[i:], "-")
		for _, l := range layouts {
			if t, err := time.Parse(l, candidate); err == nil {
				return t, nil
			}
		}
	}

	return time.Time{}, errors.New("no valid timestamp in filename")
}

// CleanOldLogs purges rotated log files in logDir matching bobrdobr-*.log and .old files.
// Files older than maxAgeDays are deleted first.
// If more than maxBackups remain, the oldest ones are deleted.
// The active log file (bobrdobr.log) is never deleted.
func CleanOldLogs(logDir string, maxBackups int, maxAgeDays int) error {
	return CleanOldLogsEx(logDir, "bobrdobr.log", maxBackups, maxAgeDays)
}

// CleanOldLogsEx is an extended version of CleanOldLogs that allows specifying the active log filename.
func CleanOldLogsEx(logDir string, activeLogName string, maxBackups int, maxAgeDays int) error {
	if logDir == "" {
		return nil
	}
	entries, err := os.ReadDir(logDir)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return err
	}

	if activeLogName == "" {
		activeLogName = "bobrdobr.log"
	}
	basePrefix := strings.TrimSuffix(activeLogName, filepath.Ext(activeLogName))

	cutoff := time.Time{}
	if maxAgeDays > 0 {
		cutoff = time.Now().Add(-time.Duration(maxAgeDays) * 24 * time.Hour)
	}

	type fileItem struct {
		path    string
		name    string
		modTime time.Time
	}
	var remaining []fileItem

	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		name := entry.Name()
		if name == activeLogName || name == "bobrdobr.log" {
			continue
		}

		matchedBase, _ := filepath.Match(basePrefix+"-*.log", name)
		matchedBobr, _ := filepath.Match("bobrdobr-*.log", name)
		isOld := strings.HasSuffix(name, ".old")

		if !matchedBase && !matchedBobr && !isOld {
			continue
		}

		filePath := filepath.Join(logDir, name)
		info, err := entry.Info()
		if err != nil {
			continue
		}

		fileTime := info.ModTime()
		if t, err := parseLogTimestamp(name); err == nil && t.Before(fileTime) {
			fileTime = t
		}

		if maxAgeDays > 0 && fileTime.Before(cutoff) {
			_ = os.Remove(filePath)
			continue
		}

		remaining = append(remaining, fileItem{
			path:    filePath,
			name:    name,
			modTime: fileTime,
		})
	}

	if maxBackups > 0 && len(remaining) > maxBackups {
		sort.Slice(remaining, func(i, j int) bool {
			if remaining[i].modTime.Equal(remaining[j].modTime) {
				return remaining[i].name > remaining[j].name
			}
			return remaining[i].modTime.After(remaining[j].modTime)
		})

		for _, item := range remaining[maxBackups:] {
			_ = os.Remove(item.path)
		}
	}

	return nil
}

// PurgeLegacyLogs scans appDir and permanently deletes legacy log files:
// bobrdobr.log, bobrdobr.log.old, bobrdobr-*.log, and any .old or .log file
// located directly in the root of appDir (without touching any subfolders).
// It also checks the log/ subfolder and deletes any leftover bobrdobr-migrated-*.log files.
func PurgeLegacyLogs(appDir string) error {
	if appDir == "" {
		return nil
	}
	appDirClean := filepath.Clean(appDir)
	entries, err := os.ReadDir(appDirClean)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return err
	}

	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		name := entry.Name()
		isLog := strings.HasSuffix(name, ".log")
		isOld := strings.HasSuffix(name, ".old")
		matchedBobr, _ := filepath.Match("bobrdobr-*.log", name)

		if isLog || isOld || matchedBobr || name == "bobrdobr.log" || name == "bobrdobr.log.old" {
			_ = os.Remove(filepath.Join(appDirClean, name))
		}
	}

	// Also check log/ subfolder for leftover migrated logs
	logDirClean := filepath.Join(appDirClean, "log")
	logEntries, err := os.ReadDir(logDirClean)
	if err == nil {
		for _, entry := range logEntries {
			if entry.IsDir() {
				continue
			}
			name := entry.Name()
			if matchedMigrated, _ := filepath.Match("bobrdobr-migrated-*.log", name); matchedMigrated {
				_ = os.Remove(filepath.Join(logDirClean, name))
			}
		}
	}

	return nil
}

// MigrateLegacyLogs is maintained as an alias to PurgeLegacyLogs for backward compatibility.
func MigrateLegacyLogs(appDir string, logDir string) error {
	return PurgeLegacyLogs(appDir)
}

// FormatEntry formats a log record to ensure [YYYY-MM-DD HH:MM:SS] [TAG] message formatting.
func FormatEntry(p []byte, t time.Time) []byte {
	ts := t.Format("2006-01-02 15:04:05")
	raw := strings.TrimRight(string(p), "\r\n")
	if raw == "" {
		return []byte("\r\n")
	}

	// Startup banners and section dividers remain clean top-level markers
	if strings.HasPrefix(raw, "===") {
		return []byte(raw + "\r\n")
	}

	lines := strings.Split(raw, "\n")
	var sb strings.Builder
	for i, line := range lines {
		trimmed := strings.TrimRight(line, "\r")
		if i == 0 {
			// Check if already formatted with [YYYY-MM-DD HH:MM:SS]
			if len(trimmed) >= 22 && trimmed[0] == '[' && trimmed[5] == '-' && trimmed[8] == '-' && trimmed[11] == ' ' && trimmed[14] == ':' && trimmed[17] == ':' && trimmed[20] == ']' {
				sb.WriteString(trimmed)
			} else if len(trimmed) >= 20 && trimmed[4] == '/' && trimmed[7] == '/' && trimmed[10] == ' ' && trimmed[13] == ':' && trimmed[16] == ':' && trimmed[19] == ' ' {
				// Strip Go standard library log prefix (e.g. "2006/01/02 15:04:05 ")
				rest := strings.TrimSpace(trimmed[20:])
				if strings.HasPrefix(rest, "[") {
					sb.WriteString(fmt.Sprintf("[%s] %s", ts, rest))
				} else {
					sb.WriteString(fmt.Sprintf("[%s] [БОБР] %s", ts, rest))
				}
			} else {
				if strings.HasPrefix(trimmed, "[") {
					sb.WriteString(fmt.Sprintf("[%s] %s", ts, trimmed))
				} else {
					sb.WriteString(fmt.Sprintf("[%s] [БОБР] %s", ts, trimmed))
				}
			}
		} else {
			// Indent stack traces or continuation lines
			sb.WriteString("    ")
			sb.WriteString(trimmed)
		}
		sb.WriteString("\r\n")
	}
	return []byte(sb.String())
}

// Write safely writes the log record to the persistent log file with rotation and sync,
// and safely attempts to mirror to stdout if available without failing on invalid stdout handles.
func (w *SafeLogWriter) Write(p []byte) (n int, err error) {
	w.mu.Lock()
	defer w.mu.Unlock()

	formatted := FormatEntry(p, time.Now())

	// 1. Check size limit and rotate if necessary
	if w.file != nil && w.currentSize+int64(len(formatted)) > w.maxSize {
		w.rotateLocked()
	}

	// Ensure file is open
	if w.file == nil {
		f, oerr := os.OpenFile(w.logPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
		if oerr == nil {
			w.file = f
			if fi, serr := f.Stat(); serr == nil {
				w.currentSize = fi.Size()
			}
		}
	}

	// 2. Write to persistent log file and sync
	if w.file != nil {
		nw, werr := w.file.Write(formatted)
		if werr == nil {
			w.currentSize += int64(nw)
			_ = w.file.Sync()
		}
	}

	// 3. Mirror to stdout safely (ignoring any write error on Windows GUI subsystem)
	if w.stdout != nil {
		_, _ = w.stdout.Write(formatted)
	}

	return len(p), nil
}

// Setup initializes the global standard logger with SafeLogWriter,
// purges legacy log files from appDir and leftover migrated logs in appDir/log/,
// configures log flags, and writes the application startup banner.
func Setup(appDir string, appVersion string) (*SafeLogWriter, error) {
	if appDir == "" {
		appDir = "."
	}
	logDir := filepath.Join(appDir, "log")
	if err := os.MkdirAll(logDir, 0755); err != nil {
		return nil, fmt.Errorf("failed to create log directory: %w", err)
	}

	// 1. Purge legacy logs from appDir and leftover migrated logs in logDir
	_ = PurgeLegacyLogs(appDir)

	// 2. Initialize SafeLogWriter (which also prunes old logs on startup)
	logPath := filepath.Join(logDir, "bobrdobr.log")
	writer, err := NewSafeLogWriter(logPath, DefaultMaxLogSize)
	if err != nil {
		return nil, err
	}

	// Disable Go's default date/time flags so SafeLogWriter formats [YYYY-MM-DD HH:MM:SS]
	log.SetFlags(0)
	log.SetOutput(writer)

	// Write clear banner: === BobrDobr VPN v1.2.2 Started [PID: %d] ===
	log.Printf("=== BobrDobr VPN v%s Started [PID: %d] ===", appVersion, os.Getpid())

	return writer, nil
}
