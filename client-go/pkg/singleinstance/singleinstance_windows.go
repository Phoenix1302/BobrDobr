//go:build windows

package singleinstance

import (
	"context"
	"errors"
	"fmt"
	"os/exec"
	"strconv"
	"strings"
	"sync"
	"time"
	"unsafe"

	"golang.org/x/sys/windows"
)

var (
	modkernel32                  = windows.NewLazySystemDLL("kernel32.dll")
	procWaitNamedPipeW           = modkernel32.NewProc("WaitNamedPipeW")
	moduser32                    = windows.NewLazySystemDLL("user32.dll")
	procAllowSetForegroundWindow = moduser32.NewProc("AllowSetForegroundWindow")
	procRegisterWindowMessageW   = moduser32.NewProc("RegisterWindowMessageW")
	procPostMessageW             = moduser32.NewProc("PostMessageW")
	procEnumWindows              = moduser32.NewProc("EnumWindows")
	procGetWindowThreadProcessId = moduser32.NewProc("GetWindowThreadProcessId")
	procShowWindow               = moduser32.NewProc("ShowWindow")
	procBringWindowToTop         = moduser32.NewProc("BringWindowToTop")
	procSetForegroundWindow      = moduser32.NewProc("SetForegroundWindow")
)

type SingleInstance struct {
	mutexName   string
	pipeName    string
	mutexHandle windows.Handle
	pipeServer  windows.Handle
	mu          sync.Mutex
	cancelFunc  context.CancelFunc
	running     bool
}

// New creates a new SingleInstance manager.
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

func createSecurityAttributes(sddl string) (*windows.SecurityAttributes, error) {
	sd, err := windows.SecurityDescriptorFromString(sddl)
	if err != nil {
		return nil, err
	}
	return &windows.SecurityAttributes{
		Length:             uint32(unsafe.Sizeof(windows.SecurityAttributes{})),
		SecurityDescriptor: sd,
		InheritHandle:      0,
	}, nil
}

// TryAcquire attempts to acquire the unified single instance mutex with cross-integrity attributes.
// Also inspects legacy mutexes for backward compatibility.
// Returns true if successfully acquired and no other instance exists.
func (s *SingleInstance) TryAcquire() (bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.mutexHandle != 0 {
		return true, nil
	}

	sa, err := createSecurityAttributes(LowIntegritySDDL)
	if err != nil {
		// Fallback to nil security attributes if SDDL conversion fails
		sa = nil
	}

	namePtr, err := windows.UTF16PtrFromString(s.mutexName)
	if err != nil {
		return false, err
	}

	hMutex, err := windows.CreateMutex(sa, false, namePtr)
	if err != nil {
		if errors.Is(err, windows.ERROR_ALREADY_EXISTS) || errors.Is(err, windows.ERROR_ACCESS_DENIED) {
			if hMutex != 0 {
				_ = windows.CloseHandle(hMutex)
			}
			return false, nil
		}
		return false, fmt.Errorf("CreateMutex failed: %w", err)
	}

	// Inspect legacy mutexes for backwards compatibility
	legacyNames := []string{
		`Global\BobrDobr_VPN_SingleInstance_Installed_v1`,
		`Global\BobrDobr_VPN_SingleInstance_Portable_v1`,
	}
	for _, legName := range legacyNames {
		legPtr, err := windows.UTF16PtrFromString(legName)
		if err == nil {
			hLeg, _ := windows.OpenMutex(windows.SYNCHRONIZE, false, legPtr)
			if hLeg != 0 {
				_ = windows.CloseHandle(hLeg)
				_ = windows.CloseHandle(hMutex)
				return false, nil
			}
		}
	}

	s.mutexHandle = hMutex
	return true, nil
}

// Release closes the single-instance mutex handle.
func (s *SingleInstance) Release() error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.mutexHandle != 0 {
		err := windows.CloseHandle(s.mutexHandle)
		s.mutexHandle = 0
		return err
	}
	return nil
}

// Close implements io.Closer, stopping the IPC server and releasing the mutex.
func (s *SingleInstance) Close() error {
	_ = s.StopIPCServer()
	return s.Release()
}

// StartIPCServer starts a named pipe server listening on s.pipeName.
func (s *SingleInstance) StartIPCServer(ctx context.Context, handler MessageHandler) error {
	s.mu.Lock()
	if s.running {
		s.mu.Unlock()
		return errors.New("IPC server is already running")
	}
	serverCtx, cancel := context.WithCancel(ctx)
	s.cancelFunc = cancel
	s.running = true
	s.mu.Unlock()

	go s.serverLoop(serverCtx, handler)
	return nil
}

// StopIPCServer cleanly stops the named pipe server.
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

	if s.pipeServer != 0 {
		_ = windows.CloseHandle(s.pipeServer)
		s.pipeServer = 0
	}

	// Wake up any blocking ConnectNamedPipe by a fast ping connect
	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()
	_, _ = SendMessage(ctx, s.pipeName, MsgPing)

	return nil
}

func (s *SingleInstance) serverLoop(ctx context.Context, handler MessageHandler) {
	pipeNamePtr, err := windows.UTF16PtrFromString(s.pipeName)
	if err != nil {
		return
	}

	sa, _ := createSecurityAttributes(LowIntegritySDDL)

	for {
		select {
		case <-ctx.Done():
			return
		default:
		}

		// Create instance of named pipe
		hPipe, err := windows.CreateNamedPipe(
			pipeNamePtr,
			windows.PIPE_ACCESS_DUPLEX,
			windows.PIPE_TYPE_MESSAGE|windows.PIPE_READMODE_MESSAGE|windows.PIPE_WAIT,
			windows.PIPE_UNLIMITED_INSTANCES,
			4096,
			4096,
			50,
			sa,
		)
		if err != nil {
			select {
			case <-ctx.Done():
				return
			case <-time.After(100 * time.Millisecond):
				continue
			}
		}

		s.mu.Lock()
		s.pipeServer = hPipe
		s.mu.Unlock()

		// Wait for client to connect
		err = windows.ConnectNamedPipe(hPipe, nil)
		if err != nil && !errors.Is(err, windows.ERROR_PIPE_CONNECTED) {
			_ = windows.CloseHandle(hPipe)
			select {
			case <-ctx.Done():
				return
			default:
				continue
			}
		}

		select {
		case <-ctx.Done():
			_ = windows.DisconnectNamedPipe(hPipe)
			_ = windows.CloseHandle(hPipe)
			return
		default:
		}

		// Handle client connection in a separate goroutine
		go func(pipe windows.Handle) {
			defer func() {
				_ = windows.FlushFileBuffers(pipe)
				_ = windows.DisconnectNamedPipe(pipe)
				_ = windows.CloseHandle(pipe)
			}()

			buf := make([]byte, 4096)
			var bytesRead uint32
			err := windows.ReadFile(pipe, buf, &bytesRead, nil)
			if err != nil || bytesRead == 0 {
				return
			}

			reqMsg := strings.TrimSpace(string(buf[:bytesRead]))
			var respMsg string

			switch reqMsg {
			case MsgPing:
				respMsg = RespPong
			case MsgActivate:
				_ = ActivateExistingWindow()
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

			var written uint32
			_ = windows.WriteFile(pipe, []byte(respMsg+"\n"), &written, nil)
		}(hPipe)
	}
}

// SendMessage connects to the named pipe and sends a message, returning the response.
func SendMessage(ctx context.Context, pipeName string, msg string) (string, error) {
	if pipeName == "" {
		pipeName = DefaultPipeName
	}
	pipeNamePtr, err := windows.UTF16PtrFromString(pipeName)
	if err != nil {
		return "", err
	}

	deadline, hasDeadline := ctx.Deadline()
	for {
		select {
		case <-ctx.Done():
			return "", ctx.Err()
		default:
		}

		h, err := windows.CreateFile(
			pipeNamePtr,
			windows.GENERIC_READ|windows.GENERIC_WRITE,
			0,
			nil,
			windows.OPEN_EXISTING,
			0,
			0,
		)
		if err == nil {
			defer windows.CloseHandle(h)

			var written uint32
			sendBytes := []byte(strings.TrimSpace(msg) + "\n")
			err = windows.WriteFile(h, sendBytes, &written, nil)
			if err != nil {
				return "", fmt.Errorf("failed to write to pipe: %w", err)
			}

			buf := make([]byte, 4096)
			var readBytes uint32
			err = windows.ReadFile(h, buf, &readBytes, nil)
			if err != nil && !errors.Is(err, windows.ERROR_BROKEN_PIPE) {
				return "", fmt.Errorf("failed to read from pipe: %w", err)
			}

			return strings.TrimSpace(string(buf[:readBytes])), nil
		}

		if errors.Is(err, windows.ERROR_PIPE_BUSY) {
			if procWaitNamedPipeW.Find() == nil {
				_, _, _ = procWaitNamedPipeW.Call(uintptr(unsafe.Pointer(pipeNamePtr)), 100)
			}
		} else if errors.Is(err, windows.ERROR_FILE_NOT_FOUND) {
			// Pipe server might not be ready yet
		} else {
			return "", fmt.Errorf("failed to connect to pipe: %w", err)
		}

		if hasDeadline && time.Now().After(deadline) {
			return "", ErrTimeout
		}

		select {
		case <-ctx.Done():
			return "", ctx.Err()
		case <-time.After(50 * time.Millisecond):
		}
	}
}

// FindOtherProcesses uses CreateToolhelp32Snapshot to find other BobrDobr VPN processes.
func FindOtherProcesses() ([]ProcessInfo, error) {
	snapshot, err := windows.CreateToolhelp32Snapshot(windows.TH32CS_SNAPPROCESS, 0)
	if err != nil {
		return nil, fmt.Errorf("CreateToolhelp32Snapshot failed: %w", err)
	}
	defer windows.CloseHandle(snapshot)

	var entry windows.ProcessEntry32
	entry.Size = uint32(unsafe.Sizeof(entry))

	if err := windows.Process32First(snapshot, &entry); err != nil {
		return nil, fmt.Errorf("Process32First failed: %w", err)
	}

	myPID := windows.GetCurrentProcessId()
	var results []ProcessInfo

	for {
		pid := int(entry.ProcessID)
		name := windows.UTF16ToString(entry.ExeFile[:])
		nameLower := strings.ToLower(name)

		if pid != int(myPID) && pid > 0 {
			if strings.Contains(nameLower, "bobrdobr") {
				fullPath := queryProcessImagePath(uint32(pid))
				pathLower := strings.ToLower(fullPath)

				// Exclude dev tools/browsers
				ignored := false
				for _, ign := range []string{"code.exe", "devenv", "chrome", "msedge", "firefox"} {
					if strings.Contains(pathLower, ign) {
						ignored = true
						break
					}
				}

				if !ignored {
					isInstalled := strings.Contains(pathLower, `\programs\bobrdobr`) ||
						strings.Contains(pathLower, `\program files`)

					results = append(results, ProcessInfo{
						PID:         pid,
						ExeName:     name,
						ExePath:     fullPath,
						IsInstalled: isInstalled,
					})
				}
			}
		}

		if err := windows.Process32Next(snapshot, &entry); err != nil {
			break
		}
	}

	return results, nil
}

func queryProcessImagePath(pid uint32) string {
	h, err := windows.OpenProcess(windows.PROCESS_QUERY_LIMITED_INFORMATION, false, pid)
	if err != nil {
		return ""
	}
	defer windows.CloseHandle(h)

	buf := make([]uint16, windows.MAX_PATH)
	size := uint32(len(buf))
	err = windows.QueryFullProcessImageName(h, 0, &buf[0], &size)
	if err != nil {
		return ""
	}
	return windows.UTF16ToString(buf[:size])
}

// TerminateProcessByPID safely terminates a process given its PID.
func TerminateProcessByPID(pid int, timeout time.Duration) error {
	if pid <= 0 {
		return nil
	}

	// 1. Try Win32 OpenProcess with PROCESS_TERMINATE
	h, err := windows.OpenProcess(windows.PROCESS_TERMINATE, false, uint32(pid))
	if err == nil {
		defer windows.CloseHandle(h)
		if termErr := windows.TerminateProcess(h, 1); termErr == nil {
			return nil
		}
	}

	// 2. Fallback to taskkill /F /T /PID
	cmd := exec.Command("taskkill", "/F", "/T", "/PID", strconv.Itoa(pid))
	cmd.SysProcAttr = &windows.SysProcAttr{HideWindow: true}
	return cmd.Run()
}

// SetMockProcesses is a stub on Windows for cross-platform test compatibility.
func SetMockProcesses(procs []ProcessInfo) {}

// ActivateExistingWindow allows the existing window to set foreground focus
// and signals it via registered window message / ShowWindow.
func ActivateExistingWindow() error {
	if procAllowSetForegroundWindow.Find() == nil {
		_, _, _ = procAllowSetForegroundWindow.Call(uintptr(0xFFFFFFFF))
	}

	msgName, _ := windows.UTF16PtrFromString("BobrDobr_VPN_Activate_Window_Msg")
	if procRegisterWindowMessageW.Find() == nil && procPostMessageW.Find() == nil {
		msgID, _, _ := procRegisterWindowMessageW.Call(uintptr(unsafe.Pointer(msgName)))
		if msgID != 0 {
			hwndBroadcast := uintptr(0xFFFF)
			_, _, _ = procPostMessageW.Call(hwndBroadcast, msgID, 0, 0)
		}
	}

	// Also enumerate windows to find BobrDobr window and restore it
	enumCallback := windows.NewCallback(func(hwnd windows.Handle, lParam uintptr) uintptr {
		var pid uint32
		if procGetWindowThreadProcessId.Find() == nil {
			_, _, _ = procGetWindowThreadProcessId.Call(uintptr(hwnd), uintptr(unsafe.Pointer(&pid)))
		}
		if pid != 0 && pid != windows.GetCurrentProcessId() {
			procPath := queryProcessImagePath(pid)
			if strings.Contains(strings.ToLower(procPath), "bobrdobr") {
				if procShowWindow.Find() == nil {
					_, _, _ = procShowWindow.Call(uintptr(hwnd), 9) // SW_RESTORE
				}
				if procBringWindowToTop.Find() == nil {
					_, _, _ = procBringWindowToTop.Call(uintptr(hwnd))
				}
				if procSetForegroundWindow.Find() == nil {
					_, _, _ = procSetForegroundWindow.Call(uintptr(hwnd))
				}
				return 0 // Stop enumerating
			}
		}
		return 1 // Continue
	})

	if procEnumWindows.Find() == nil {
		_, _, _ = procEnumWindows.Call(enumCallback, 0)
	}

	return nil
}
