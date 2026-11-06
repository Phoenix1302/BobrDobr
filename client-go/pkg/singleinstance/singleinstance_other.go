//go:build !windows

package singleinstance

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"
)

var (
	// mockProcesses allows tests on unix to verify process discovery logic
	mockProcessesMu sync.RWMutex
	mockProcesses   []ProcessInfo
)

// SetMockProcesses sets a mocked process list for non-windows testing.
func SetMockProcesses(procs []ProcessInfo) {
	mockProcessesMu.Lock()
	defer mockProcessesMu.Unlock()
	mockProcesses = procs
}

type SingleInstance struct {
	mutexName  string
	pipeName   string
	listener   net.Listener
	mu         sync.Mutex
	cancelFunc context.CancelFunc
	running    bool
	isAcquired bool
}

// Global lock to simulate cross-process mutex in non-windows environments
var (
	globalLockMu sync.Mutex
	activeLocks  = make(map[string]bool)
)

// New creates a new SingleInstance manager for non-Windows platforms.
func New(mutexName, pipeName string) *SingleInstance {
	if mutexName == "" {
		mutexName = DefaultMutexName
	}
	if pipeName == "" {
		pipeName = DefaultPipeName
	}
	return &SingleInstance{
		mutexName: mutexName,
		pipeName:  pipeName,
	}
}

func getSocketPath(name string) string {
	clean := strings.ReplaceAll(name, `\\.\pipe\`, "")
	clean = strings.ReplaceAll(clean, `\`, "_")
	clean = strings.ReplaceAll(clean, `/`, "_")
	return filepath.Join(os.TempDir(), clean+".sock")
}

// TryAcquire attempts to acquire the instance lock.
func (s *SingleInstance) TryAcquire() (bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.isAcquired {
		return true, nil
	}

	globalLockMu.Lock()
	defer globalLockMu.Unlock()

	if activeLocks[s.mutexName] {
		return false, nil
	}

	activeLocks[s.mutexName] = true
	s.isAcquired = true
	return true, nil
}

// Release releases the acquired lock.
func (s *SingleInstance) Release() error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if !s.isAcquired {
		return nil
	}

	globalLockMu.Lock()
	defer globalLockMu.Unlock()

	delete(activeLocks, s.mutexName)
	s.isAcquired = false
	return nil
}

// Close implements io.Closer.
func (s *SingleInstance) Close() error {
	_ = s.StopIPCServer()
	return s.Release()
}

// StartIPCServer starts the IPC server using a Unix domain socket.
func (s *SingleInstance) StartIPCServer(ctx context.Context, handler MessageHandler) error {
	s.mu.Lock()
	if s.running {
		s.mu.Unlock()
		return errors.New("IPC server is already running")
	}

	sockPath := getSocketPath(s.pipeName)
	_ = os.Remove(sockPath)

	l, err := net.Listen("unix", sockPath)
	if err != nil {
		s.mu.Unlock()
		return fmt.Errorf("failed to listen on unix socket %s: %w", sockPath, err)
	}

	serverCtx, cancel := context.WithCancel(ctx)
	s.listener = l
	s.cancelFunc = cancel
	s.running = true
	s.mu.Unlock()

	go s.serverLoop(serverCtx, l, handler)
	return nil
}

// StopIPCServer cleanly stops the IPC server.
func (s *SingleInstance) StopIPCServer() error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if !s.running {
		return nil
	}
	s.running = false

	if s.cancelFunc != nil {
		s.cancelFunc()
		s.cancelFunc = nil
	}

	var err error
	if s.listener != nil {
		err = s.listener.Close()
		s.listener = nil
	}

	sockPath := getSocketPath(s.pipeName)
	_ = os.Remove(sockPath)
	return err
}

func (s *SingleInstance) serverLoop(ctx context.Context, l net.Listener, handler MessageHandler) {
	for {
		conn, err := l.Accept()
		if err != nil {
			select {
			case <-ctx.Done():
				return
			default:
				return
			}
		}

		go func(c net.Conn) {
			defer c.Close()

			reader := bufio.NewReader(c)
			line, err := reader.ReadString('\n')
			if err != nil {
				return
			}

			reqMsg := strings.TrimSpace(line)
			var respMsg string

			switch reqMsg {
			case MsgPing:
				respMsg = RespPong
			case MsgActivate:
				if handler != nil {
					resp, _ := handler(reqMsg)
					if resp != "" {
						respMsg = resp
					} else {
						respMsg = RespOK
					}
				} else {
					respMsg = RespOK
				}
			case MsgKill:
				if handler != nil {
					resp, _ := handler(reqMsg)
					if resp != "" {
						respMsg = resp
					} else {
						respMsg = RespOK
					}
				} else {
					respMsg = RespOK
				}
			default:
				if handler != nil {
					resp, err := handler(reqMsg)
					if err != nil {
						respMsg = fmt.Sprintf("ERROR: %v", err)
					} else {
						respMsg = resp
					}
				} else {
					respMsg = "UNKNOWN_COMMAND"
				}
			}

			_, _ = c.Write([]byte(respMsg + "\n"))
		}(conn)
	}
}

// SendMessage connects to the IPC server and sends a message string.
func SendMessage(ctx context.Context, pipeName string, msg string) (string, error) {
	if pipeName == "" {
		pipeName = DefaultPipeName
	}
	sockPath := getSocketPath(pipeName)

	var d net.Dialer
	conn, err := d.DialContext(ctx, "unix", sockPath)
	if err != nil {
		return "", fmt.Errorf("failed to connect to unix socket %s: %w", sockPath, err)
	}
	defer conn.Close()

	if deadline, ok := ctx.Deadline(); ok {
		_ = conn.SetDeadline(deadline)
	}

	_, err = conn.Write([]byte(strings.TrimSpace(msg) + "\n"))
	if err != nil {
		return "", fmt.Errorf("failed to write to IPC socket: %w", err)
	}

	reader := bufio.NewReader(conn)
	line, err := reader.ReadString('\n')
	if err != nil {
		return "", fmt.Errorf("failed to read from IPC socket: %w", err)
	}

	return strings.TrimSpace(line), nil
}

// FindOtherProcesses scans running processes. On non-windows, returns mock list if set,
// or parses /proc if available.
func FindOtherProcesses() ([]ProcessInfo, error) {
	mockProcessesMu.RLock()
	if len(mockProcesses) > 0 {
		defer mockProcessesMu.RUnlock()
		return mockProcesses, nil
	}
	mockProcessesMu.RUnlock()

	entries, err := os.ReadDir("/proc")
	if err != nil {
		return nil, nil
	}

	myPID := os.Getpid()
	var results []ProcessInfo

	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		pid, err := strconv.Atoi(entry.Name())
		if err != nil || pid <= 0 || pid == myPID {
			continue
		}

		commBytes, err := os.ReadFile(filepath.Join("/proc", entry.Name(), "comm"))
		if err != nil {
			continue
		}
		comm := strings.TrimSpace(string(commBytes))

		if strings.Contains(strings.ToLower(comm), "bobrdobr") {
			exePath, _ := os.Readlink(filepath.Join("/proc", entry.Name(), "exe"))
			results = append(results, ProcessInfo{
				PID:         pid,
				ExeName:     comm,
				ExePath:     exePath,
				IsInstalled: strings.Contains(exePath, "/opt/"),
			})
		}
	}

	return results, nil
}

// TerminateProcessByPID sends SIGTERM, then SIGKILL on non-Windows.
func TerminateProcessByPID(pid int, timeout time.Duration) error {
	if pid <= 0 {
		return nil
	}
	proc, err := os.FindProcess(pid)
	if err != nil {
		return err
	}

	_ = proc.Signal(syscall.SIGTERM)

	done := make(chan error, 1)
	go func() {
		// Wait or check if still alive
		for i := 0; i < int(timeout/time.Millisecond)/50; i++ {
			time.Sleep(50 * time.Millisecond)
			if err := proc.Signal(syscall.Signal(0)); err != nil {
				done <- nil
				return
			}
		}
		_ = proc.Signal(syscall.SIGKILL)
		done <- nil
	}()

	select {
	case <-done:
		return nil
	case <-time.After(timeout + 500*time.Millisecond):
		_ = proc.Signal(syscall.SIGKILL)
		return nil
	}
}

// ActivateExistingWindow is a no-op on non-Windows.
func ActivateExistingWindow() error {
	return nil
}
