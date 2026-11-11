package vpn

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

// AmneziaConfig contains settings for launching an AmneziaWG tunnel.
type AmneziaConfig struct {
	BinaryPath    string   `json:"binary_path"`
	ConfigPath    string   `json:"config_path"`
	ConfigContent string   `json:"config_content"`
	InterfaceName string   `json:"interface_name"`
	WintunDLLDir  string   `json:"wintun_dll_dir,omitempty"`
	ExtraArgs     []string `json:"extra_args,omitempty"`
}

// AmneziaSupervisor manages the lifecycle of an AmneziaWG daemon process.
type AmneziaSupervisor struct {
	binaryPath string
	jobObject  *JobObject
	listeners  []EventListener
	mu         sync.Mutex
	cmd        *exec.Cmd
	state      State
	tempConfig string
	stopCh     chan struct{}
	exitCh     chan struct{}
	cmdFactory func(ctx context.Context, name string, args ...string) *exec.Cmd
}

// NewAmneziaSupervisor creates a new AmneziaWG supervisor.
func NewAmneziaSupervisor(binaryPath string, job *JobObject) *AmneziaSupervisor {
	return &AmneziaSupervisor{
		binaryPath: binaryPath,
		jobObject:  job,
		state:      StateDisconnected,
		cmdFactory: exec.CommandContext,
	}
}

// SetCmdFactory allows mocking subprocess execution for unit tests.
func (s *AmneziaSupervisor) SetCmdFactory(fn func(ctx context.Context, name string, args ...string) *exec.Cmd) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.cmdFactory = fn
}

// AddListener registers an event listener.
func (s *AmneziaSupervisor) AddListener(l EventListener) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.listeners = append(s.listeners, l)
}

// State returns the current connection state.
func (s *AmneziaSupervisor) State() State {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.state
}

// IsRunning returns true if the daemon process is active.
func (s *AmneziaSupervisor) IsRunning() bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.cmd != nil && s.cmd.Process != nil && s.state != StateDisconnected && s.state != StateError
}

// PID returns the current process ID if running, or 0.
func (s *AmneziaSupervisor) PID() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.cmd != nil && s.cmd.Process != nil {
		return s.cmd.Process.Pid
	}
	return 0
}

func (s *AmneziaSupervisor) emit(state State, message, channel string, details map[string]interface{}) {
	s.mu.Lock()
	s.state = state
	listeners := make([]EventListener, len(s.listeners))
	copy(listeners, s.listeners)
	s.mu.Unlock()

	ev := Event{
		State:     state,
		Message:   message,
		Channel:   channel,
		Timestamp: time.Now(),
		Details:   details,
	}

	for _, l := range listeners {
		l(ev)
	}
}

// Start spawns amneziawg-go and monitors output for connection events.
func (s *AmneziaSupervisor) Start(ctx context.Context, cfg AmneziaConfig) error {
	s.mu.Lock()
	if s.cmd != nil && s.cmd.Process != nil {
		s.mu.Unlock()
		// Cleanly stop any existing instance before starting anew
		_ = s.Stop(ctx)
		s.mu.Lock()
	}

	bin := cfg.BinaryPath
	if bin == "" {
		bin = s.binaryPath
	}
	if bin == "" {
		bin = "amneziawg-go"
	}

	iface := strings.TrimSpace(cfg.InterfaceName)
	if iface == "" {
		iface = "bobr0"
	}

	activeConfigPath := cfg.ConfigPath

	// Handle in-memory config content
	if cfg.ConfigContent != "" {
		tmpFile, err := os.CreateTemp("", "awg_*.conf")
		if err != nil {
			s.mu.Unlock()
			return fmt.Errorf("failed to create temporary config: %w", err)
		}
		if _, err := tmpFile.WriteString(cfg.ConfigContent); err != nil {
			tmpFile.Close()
			_ = os.Remove(tmpFile.Name())
			s.mu.Unlock()
			return fmt.Errorf("failed to write temporary config: %w", err)
		}
		tmpFile.Close()
		activeConfigPath = tmpFile.Name()
		s.tempConfig = activeConfigPath
	} else if activeConfigPath == "" {
		s.mu.Unlock()
		return errors.New("neither ConfigPath nor ConfigContent was provided")
	}

	var args []string
	args = append(args, "-config", activeConfigPath, "-name", iface)
	if len(cfg.ExtraArgs) > 0 {
		args = append(args, cfg.ExtraArgs...)
	}

	cmd := s.cmdFactory(context.Background(), bin, args...)
	configureAmneziaProcAttr(cmd)

	binDir := filepath.Dir(bin)
	cmd.Dir = binDir

	// Inject binary directory and Wintun DLL directory into PATH
	dirs := []string{binDir}
	if cfg.WintunDLLDir != "" && cfg.WintunDLLDir != binDir {
		dirs = append(dirs, cfg.WintunDLLDir)
	}
	pathPrefix := strings.Join(dirs, ";")

	env := os.Environ()
	pathUpdated := false
	for i, e := range env {
		if strings.HasPrefix(strings.ToUpper(e), "PATH=") {
			env[i] = fmt.Sprintf("PATH=%s;%s", pathPrefix, e[5:])
			pathUpdated = true
			break
		}
	}
	if !pathUpdated {
		env = append(env, fmt.Sprintf("PATH=%s", pathPrefix))
	}
	cmd.Env = env

	stdoutPipe, err := cmd.StdoutPipe()
	if err != nil {
		s.mu.Unlock()
		s.cleanupTempConfig()
		return fmt.Errorf("failed to open stdout pipe: %w", err)
	}

	stderrPipe, err := cmd.StderrPipe()
	if err != nil {
		s.mu.Unlock()
		s.cleanupTempConfig()
		return fmt.Errorf("failed to open stderr pipe: %w", err)
	}

	if err := cmd.Start(); err != nil {
		s.mu.Unlock()
		s.cleanupTempConfig()
		return fmt.Errorf("failed to start amnezia daemon (%s): %w", bin, err)
	}

	s.cmd = cmd
	exitCh := make(chan struct{})
	s.exitCh = exitCh
	s.stopCh = make(chan struct{})
	pid := cmd.Process.Pid
	s.mu.Unlock()

	// Assign to JobObject to ensure zero process leak
	if s.jobObject != nil {
		_ = s.jobObject.AssignProcessPID(pid)
	}

	s.emit(StateConnecting, fmt.Sprintf("AmneziaWG started (PID: %d, interface: %s)", pid, iface), "sys", map[string]interface{}{
		"pid":       pid,
		"interface": iface,
		"config":    filepath.Base(activeConfigPath),
	})

	var wg sync.WaitGroup
	wg.Add(2)

	go func() {
		defer wg.Done()
		s.scanPipe(stdoutPipe, "stdout", iface)
	}()

	go func() {
		defer wg.Done()
		s.scanPipe(stderrPipe, "stderr", iface)
	}()

	go func() {
		wg.Wait()
		_ = cmd.Wait()

		s.mu.Lock()
		s.cmd = nil
		s.cleanupTempConfig()
		s.mu.Unlock()

		close(exitCh)
		s.emit(StateDisconnected, "AmneziaWG tunnel process terminated", "sys", nil)
	}()

	return nil
}

func (s *AmneziaSupervisor) scanPipe(r io.Reader, channel, iface string) {
	scanner := bufio.NewScanner(r)
	for scanner.Scan() {
		line := scanner.Text()
		s.ParseLine(line, channel, iface)
	}
}

// ParseLine inspects stdout/stderr lines and emits state events.
func (s *AmneziaSupervisor) ParseLine(line, channel, iface string) {
	lower := strings.ToLower(line)

	// Connected states
	connectedKeywords := []string{
		"device started",
		"interface created",
		"uapi: updating configuration",
		"receiving handshake response",
		"handshake for peer",
		"tunnel is up",
		"handshake successful",
	}

	if iface != "" {
		connectedKeywords = append(connectedKeywords, fmt.Sprintf("interface %s created", strings.ToLower(iface)))
	}

	for _, kw := range connectedKeywords {
		if strings.Contains(lower, kw) {
			s.emit(StateConnected, line, channel, map[string]interface{}{"keyword": kw})
			return
		}
	}

	// Error states
	errorKeywords := []string{
		"unable to create interface",
		"unable to create wintun interface",
		"failed to setup adapter",
		"failed to setup wireguard",
		"wintun: unable to load",
		"timed out waiting for device query",
		"cannot create a file when that file already exists",
		"permission denied",
		"address already in use",
	}

	for _, kw := range errorKeywords {
		if strings.Contains(lower, kw) {
			s.emit(StateError, line, channel, map[string]interface{}{"keyword": kw})
			return
		}
	}

	// General log forwarding
	s.mu.Lock()
	currentState := s.state
	s.mu.Unlock()
	s.emit(currentState, line, channel, nil)
}

// Stop cleanly shuts down the AmneziaWG daemon process.
// WireGuard is a stateless UDP protocol with no remote session termination packets;
// killing the process cleanly releases the Wintun handle, which triggers the Wintun driver
// to dismantle the virtual adapter and routes.
func (s *AmneziaSupervisor) Stop(ctx context.Context) error {
	s.mu.Lock()
	cmd := s.cmd
	exitCh := s.exitCh
	if cmd == nil || cmd.Process == nil {
		s.mu.Unlock()
		return nil
	}
	pid := cmd.Process.Pid
	s.mu.Unlock()

	s.emit(StateDisconnecting, fmt.Sprintf("Stopping AmneziaWG tunnel (PID: %d)...", pid), "sys", nil)

	s.mu.Lock()
	if s.cmd != nil && s.cmd.Process != nil {
		_ = s.cmd.Process.Kill()
	}
	s.mu.Unlock()

	if exitCh != nil {
		select {
		case <-exitCh:
		case <-time.After(1500 * time.Millisecond):
		case <-ctx.Done():
		}
	}

	s.mu.Lock()
	s.cmd = nil
	s.cleanupTempConfig()
	s.mu.Unlock()

	return nil
}

func (s *AmneziaSupervisor) cleanupTempConfig() {
	if s.tempConfig != "" {
		_ = os.Remove(s.tempConfig)
		s.tempConfig = ""
	}
}
