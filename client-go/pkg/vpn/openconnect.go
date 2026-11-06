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

// OpenConnectConfig holds configuration for starting an OpenConnect VPN session.
type OpenConnectConfig struct {
	BinaryPath       string   `json:"binary_path"`
	Server           string   `json:"server"`
	Port             int      `json:"port"`
	Username         string   `json:"username"`
	Password         string   `json:"-"` // Never logged or exposed in JSON/CLI
	Protocol         string   `json:"protocol"`
	Script           string   `json:"script"`
	CamouflageSecret string   `json:"camouflage_secret,omitempty"`
	ConnectURL       string   `json:"connect_url,omitempty"`
	Group            string   `json:"group,omitempty"`
	ExtraArgs        []string `json:"extra_args,omitempty"`
}

// OpenConnectSupervisor manages the OpenConnect process lifecycle.
type OpenConnectSupervisor struct {
	binaryPath string
	jobObject  *JobObject
	listeners  []EventListener
	mu         sync.Mutex
	cmd        *exec.Cmd
	state      State
	exitCh     chan struct{}
	cmdFactory func(ctx context.Context, name string, args ...string) *exec.Cmd
}

// NewOpenConnectSupervisor creates a new OpenConnect supervisor.
func NewOpenConnectSupervisor(binaryPath string, job *JobObject) *OpenConnectSupervisor {
	return &OpenConnectSupervisor{
		binaryPath: binaryPath,
		jobObject:  job,
		state:      StateDisconnected,
		cmdFactory: exec.CommandContext,
	}
}

// SetCmdFactory allows mocking subprocess execution for unit tests.
func (s *OpenConnectSupervisor) SetCmdFactory(fn func(ctx context.Context, name string, args ...string) *exec.Cmd) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.cmdFactory = fn
}

// AddListener registers an event listener.
func (s *OpenConnectSupervisor) AddListener(l EventListener) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.listeners = append(s.listeners, l)
}

// State returns the current connection state.
func (s *OpenConnectSupervisor) State() State {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.state
}

// IsRunning returns true if the daemon process is active.
func (s *OpenConnectSupervisor) IsRunning() bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.cmd != nil && s.cmd.Process != nil && s.state != StateDisconnected && s.state != StateError
}

// PID returns the current process ID if running, or 0.
func (s *OpenConnectSupervisor) PID() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.cmd != nil && s.cmd.Process != nil {
		return s.cmd.Process.Pid
	}
	return 0
}

func (s *OpenConnectSupervisor) emit(state State, message, channel string, details map[string]interface{}) {
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

// Start launches openconnect with credentials strictly passed via stdin pipe.
func (s *OpenConnectSupervisor) Start(ctx context.Context, cfg OpenConnectConfig) error {
	s.mu.Lock()
	if s.cmd != nil && s.cmd.Process != nil {
		s.mu.Unlock()
		// Cleanly stop any existing instance before starting anew
		_ = s.Stop(ctx)
		s.mu.Lock()
	}

	server := strings.TrimSpace(cfg.Server)
	if server == "" {
		s.mu.Unlock()
		return errors.New("server address is required")
	}

	bin := cfg.BinaryPath
	if bin == "" {
		bin = s.binaryPath
	}
	if bin == "" {
		bin = "openconnect"
	}

	// Build target URL
	port := cfg.Port
	if port <= 0 {
		port = 443
	}

	targetURL := server
	if !strings.HasPrefix(targetURL, "https://") && !strings.HasPrefix(targetURL, "http://") {
		if port != 443 {
			targetURL = fmt.Sprintf("https://%s:%d", server, port)
		} else {
			targetURL = fmt.Sprintf("https://%s", server)
		}
	}

	if cfg.CamouflageSecret != "" {
		camo := strings.TrimLeft(cfg.CamouflageSecret, "/?")
		if !strings.Contains(targetURL, "?") {
			targetURL = fmt.Sprintf("%s/?%s", strings.TrimRight(targetURL, "/"), camo)
		}
	}

	// Prepare arguments: NEVER put password in args!
	args := []string{
		"--non-inter",
		"--passwd-on-stdin",
		"-v",
	}

	proto := strings.ToLower(strings.TrimSpace(cfg.Protocol))
	if proto != "" && proto != "anyconnect" {
		args = append(args, "--protocol", proto)
	}

	if cfg.Username != "" {
		args = append(args, "--user", cfg.Username)
	}

	if cfg.Group != "" {
		args = append(args, "--authgroup", cfg.Group)
	}

	if cfg.Script != "" {
		scriptArg := strings.Trim(strings.TrimSpace(cfg.Script), `"`)
		args = append(args, "--script", scriptArg)
	}

	if len(cfg.ExtraArgs) > 0 {
		args = append(args, cfg.ExtraArgs...)
	}

	args = append(args, targetURL)

	cmd := s.cmdFactory(context.Background(), bin, args...)
	configureSysProcAttr(cmd)

	binDir := filepath.Dir(bin)
	cmd.Dir = binDir

	// Ensure binary's directory is in PATH so Windows loads libopenconnect-5.dll, libgnutls-30.dll, etc.
	env := os.Environ()
	pathUpdated := false
	for i, e := range env {
		if strings.HasPrefix(strings.ToUpper(e), "PATH=") {
			env[i] = fmt.Sprintf("PATH=%s;%s", binDir, e[5:])
			pathUpdated = true
			break
		}
	}
	if !pathUpdated {
		env = append(env, fmt.Sprintf("PATH=%s", binDir))
	}
	cmd.Env = env

	stdinPipe, err := cmd.StdinPipe()
	if err != nil {
		s.mu.Unlock()
		return fmt.Errorf("failed to open stdin pipe: %w", err)
	}

	stdoutPipe, err := cmd.StdoutPipe()
	if err != nil {
		s.mu.Unlock()
		_ = stdinPipe.Close()
		return fmt.Errorf("failed to open stdout pipe: %w", err)
	}

	stderrPipe, err := cmd.StderrPipe()
	if err != nil {
		s.mu.Unlock()
		_ = stdinPipe.Close()
		return fmt.Errorf("failed to open stderr pipe: %w", err)
	}

	if err := cmd.Start(); err != nil {
		s.mu.Unlock()
		_ = stdinPipe.Close()
		return fmt.Errorf("failed to start openconnect (%s): %w", bin, err)
	}

	s.cmd = cmd
	exitCh := make(chan struct{})
	s.exitCh = exitCh
	pid := cmd.Process.Pid
	s.mu.Unlock()

	// Assign to JobObject to ensure zero process leak
	if s.jobObject != nil {
		_ = s.jobObject.AssignProcessPID(pid)
	}

	// Write password to stdin pipe and close it immediately
	go func() {
		defer stdinPipe.Close()
		if cfg.Password != "" {
			_, _ = io.WriteString(stdinPipe, cfg.Password+"\n")
		}
	}()

	s.emit(StateConnecting, fmt.Sprintf("OpenConnect started (PID: %d, server: %s)", pid, targetURL), "sys", map[string]interface{}{
		"pid":      pid,
		"server":   targetURL,
		"protocol": proto,
	})

	var wg sync.WaitGroup
	wg.Add(2)

	go func() {
		defer wg.Done()
		s.scanPipe(stdoutPipe, "stdout")
	}()

	go func() {
		defer wg.Done()
		s.scanPipe(stderrPipe, "stderr")
	}()

	go func() {
		wg.Wait()
		_ = cmd.Wait()

		s.mu.Lock()
		s.cmd = nil
		s.mu.Unlock()

		close(exitCh)
		s.emit(StateDisconnected, "OpenConnect process terminated", "sys", nil)
	}()

	return nil
}

func (s *OpenConnectSupervisor) scanPipe(r io.Reader, channel string) {
	scanner := bufio.NewScanner(r)
	for scanner.Scan() {
		line := scanner.Text()
		s.ParseLine(line, channel)
	}
}

// ParseLine inspects stdout/stderr lines and emits state events.
func (s *OpenConnectSupervisor) ParseLine(line, channel string) {
	lower := strings.ToLower(line)

	// Connected states
	connectedKeywords := []string{
		"established dtls connection",
		"esp session established",
		"connected as",
		"configured as",
		"tunnel interface",
		"session established",
		"dtls-negotiation: done",
	}

	for _, kw := range connectedKeywords {
		if strings.Contains(lower, kw) {
			s.emit(StateConnected, line, channel, map[string]interface{}{"keyword": kw})
			return
		}
	}

	// Connecting states
	connectingKeywords := []string{
		"attempting to connect",
		"connected to https",
		"got http response",
		"post https://",
	}

	for _, kw := range connectingKeywords {
		if strings.Contains(lower, kw) {
			s.emit(StateConnecting, line, channel, map[string]interface{}{"keyword": kw})
			return
		}
	}

	// Error states
	errorKeywords := []string{
		"authentication failed",
		"failed to connect",
		"user cancelled",
		"certificate validation failed",
		"ssl connection failure",
		"unknown host",
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

// Stop gracefully terminates OpenConnect by sending CTRL_BREAK / CTRL_C
// to allow sending the AnyConnect BYE packet before exit.
func (s *OpenConnectSupervisor) Stop(ctx context.Context) error {
	s.mu.Lock()
	cmd := s.cmd
	exitCh := s.exitCh
	if cmd == nil || cmd.Process == nil {
		s.mu.Unlock()
		return nil
	}
	pid := cmd.Process.Pid
	s.mu.Unlock()

	s.emit(StateDisconnecting, fmt.Sprintf("Stopping OpenConnect session (PID: %d)...", pid), "sys", nil)

	// 1. Send graceful signal so OpenConnect can send AnyConnect BYE packet
	_ = SendGracefulSignal(pid)

	// 2. Wait up to 1.5s for graceful exit
	if exitCh != nil {
		select {
		case <-exitCh:
			return nil
		case <-time.After(1500 * time.Millisecond):
		case <-ctx.Done():
		}
	}

	// 3. Fallback to SIGKILL if still running
	s.mu.Lock()
	if s.cmd != nil && s.cmd.Process != nil {
		_ = s.cmd.Process.Kill()
	}
	s.mu.Unlock()

	// 4. Wait for exitCh to close after Kill
	if exitCh != nil {
		select {
		case <-exitCh:
		case <-time.After(1000 * time.Millisecond):
		}
	}

	s.mu.Lock()
	s.cmd = nil
	s.mu.Unlock()

	return nil
}
