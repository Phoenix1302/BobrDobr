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
	InterfaceName    string   `json:"interface_name,omitempty"`
	PhysicalGateway  string   `json:"physical_gateway,omitempty"`
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
	stdinPipe  io.WriteCloser
	state      State
	exitCh     chan struct{}
	cmdFactory func(ctx context.Context, name string, args ...string) *exec.Cmd
}

// isWorkerBinary checks if the binary is the pure-Go openconnect-worker.
func isWorkerBinary(binPath string) bool {
	base := strings.ToLower(filepath.Base(binPath))
	return strings.Contains(base, "worker") || (!strings.HasPrefix(base, "openconnect.") && base != "openconnect")
}

// resolveDefaultBinary searches for openconnect-worker.exe first, falling back to openconnect.exe.
func resolveDefaultBinary() string {
	candidates := []string{
		"openconnect-worker.exe",
		"openconnect-worker",
		"bin/openconnect-worker.exe",
		"bin/windows/openconnect-worker.exe",
		"openconnect.exe",
		"openconnect",
	}
	for _, c := range candidates {
		if path, err := exec.LookPath(c); err == nil {
			return path
		}
		if _, err := os.Stat(c); err == nil {
			abs, _ := filepath.Abs(c)
			return abs
		}
	}
	return "openconnect-worker.exe"
}

// NewOpenConnectSupervisor creates a new OpenConnect supervisor.
func NewOpenConnectSupervisor(binaryPath string, job *JobObject) *OpenConnectSupervisor {
	if binaryPath == "" {
		binaryPath = resolveDefaultBinary()
	}
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

// Start launches openconnect-worker (or openconnect fallback) with credentials passed via stdin pipe.
// The stdin pipe is kept open during tunnel lifetime to enable graceful CSTP BYE termination upon closure.
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
		bin = resolveDefaultBinary()
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

	// Prepare arguments according to worker vs legacy binary
	isWorker := isWorkerBinary(bin)
	var args []string
	if isWorker {
		args = []string{
			"--stdin-control",
			"--passwd-on-stdin",
		}

		if cfg.Username != "" {
			args = append(args, "--user", cfg.Username)
		}

		if cfg.Group != "" {
			args = append(args, "--authgroup", cfg.Group)
		}

		if cfg.InterfaceName != "" {
			args = append(args, "--interface", cfg.InterfaceName)
		}

		if len(cfg.ExtraArgs) > 0 {
			args = append(args, cfg.ExtraArgs...)
		}

		args = append(args, targetURL)
	} else {
		// Legacy openconnect.exe fallback
		args = []string{
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

		if cfg.InterfaceName != "" {
			args = append(args, "--interface", cfg.InterfaceName)
		}

		if cfg.Script != "" {
			scriptArg := strings.Trim(strings.TrimSpace(cfg.Script), `"`)
			args = append(args, "--script", scriptArg)
		}

		if len(cfg.ExtraArgs) > 0 {
			args = append(args, cfg.ExtraArgs...)
		}

		args = append(args, targetURL)
	}

	cmd := s.cmdFactory(context.Background(), bin, args...)
	configureOpenConnectProcAttr(cmd)

	binDir := filepath.Dir(bin)
	cmd.Dir = binDir

	// Ensure binary's directory is in PATH for dependencies
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
	if cfg.PhysicalGateway != "" {
		env = append(env, fmt.Sprintf("PHYSICAL_GW=%s", cfg.PhysicalGateway))
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
	s.stdinPipe = stdinPipe
	exitCh := make(chan struct{})
	s.exitCh = exitCh
	pid := cmd.Process.Pid
	s.mu.Unlock()

	// Assign to JobObject to ensure zero process leak
	if s.jobObject != nil {
		_ = s.jobObject.AssignProcessPID(pid)
	}

	// Write password to stdin pipe and KEEP PIPE OPEN!
	// Closing s.stdinPipe in Stop() signals graceful termination (CSTP BYE packet).
	if cfg.Password != "" {
		_, _ = io.WriteString(stdinPipe, cfg.Password+"\n")
	} else {
		_, _ = io.WriteString(stdinPipe, "\n")
	}

	s.emit(StateConnecting, fmt.Sprintf("OpenConnect started (PID: %d, server: %s)", pid, targetURL), "sys", map[string]interface{}{
		"pid":      pid,
		"server":   targetURL,
		"protocol": cfg.Protocol,
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
		if s.stdinPipe != nil {
			_ = s.stdinPipe.Close()
			s.stdinPipe = nil
		}
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
		"cstp tunnel established",
	}

	for _, kw := range connectedKeywords {
		if strings.Contains(lower, kw) {
			s.emit(StateConnected, line, channel, map[string]interface{}{"keyword": kw})
			return
		}
	}

	// Disconnecting / Graceful termination states
	disconnectingKeywords := []string{
		"user cancelled",
		"user detached",
		"logout of session completed",
		"session terminated",
		"bye packet",
	}

	for _, kw := range disconnectingKeywords {
		if strings.Contains(lower, kw) {
			s.emit(StateDisconnecting, line, channel, map[string]interface{}{"keyword": kw})
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

// Stop gracefully terminates OpenConnect by closing the standard input pipe.
// The pure-Go worker intercepts EOF on stdin, sends AnyConnect CSTP BYE packet
// to the server, resets network routes, closes Wintun and exits in ~100-300ms.
func (s *OpenConnectSupervisor) Stop(ctx context.Context) error {
	s.mu.Lock()
	cmd := s.cmd
	stdinPipe := s.stdinPipe
	exitCh := s.exitCh
	if cmd == nil || cmd.Process == nil {
		if stdinPipe != nil {
			_ = stdinPipe.Close()
			s.stdinPipe = nil
		}
		s.mu.Unlock()
		return nil
	}
	pid := cmd.Process.Pid

	// 1. Close stdin pipe to signal graceful shutdown (worker sends AnyConnect CSTP BYE packet)
	if stdinPipe != nil {
		_ = stdinPipe.Close()
		s.stdinPipe = nil
	}
	s.mu.Unlock()

	s.emit(StateDisconnecting, fmt.Sprintf("Stopping OpenConnect session (PID: %d)...", pid), "sys", map[string]interface{}{"pid": pid})

	// 2. Wait up to 3.5s for graceful exit to allow sending BYE packet
	if exitCh != nil {
		select {
		case <-exitCh:
			s.emit(StateDisconnected, fmt.Sprintf("OpenConnect session terminated cleanly (PID: %d)", pid), "sys", map[string]interface{}{"pid": pid, "clean": true})
			return nil
		case <-time.After(3500 * time.Millisecond):
			s.emit(StateDisconnecting, fmt.Sprintf("OpenConnect (PID: %d) did not terminate within graceful timeout (3.5s), forcing kill...", pid), "sys", map[string]interface{}{"pid": pid})
		case <-ctx.Done():
			s.emit(StateDisconnecting, fmt.Sprintf("Context cancelled while waiting for OpenConnect (PID: %d) exit", pid), "sys", map[string]interface{}{"pid": pid})
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
			s.emit(StateDisconnected, fmt.Sprintf("OpenConnect forcibly terminated (PID: %d)", pid), "sys", map[string]interface{}{"pid": pid, "clean": false})
		case <-time.After(1000 * time.Millisecond):
		}
	}

	s.mu.Lock()
	if s.stdinPipe != nil {
		_ = s.stdinPipe.Close()
		s.stdinPipe = nil
	}
	s.cmd = nil
	s.mu.Unlock()

	return nil
}
