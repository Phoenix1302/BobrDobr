package vpn

import (
	"context"
	"os/exec"
	"strings"
	"sync"
	"testing"
	"time"
)

func TestOpenConnect_ParseLine(t *testing.T) {
	sup := NewOpenConnectSupervisor("openconnect", nil)

	var lastEvent Event
	var mu sync.Mutex
	sup.AddListener(func(ev Event) {
		mu.Lock()
		defer mu.Unlock()
		lastEvent = ev
	})

	tests := []struct {
		name          string
		line          string
		expectedState State
	}{
		{
			name:          "Attempting to connect emits Connecting",
			line:          "Attempting to connect to server 1.2.3.4:443",
			expectedState: StateConnecting,
		},
		{
			name:          "Connected to HTTPS emits Connecting",
			line:          "Connected to HTTPS on 1.2.3.4 with ciphersuite TLS_AES_256_GCM_SHA384",
			expectedState: StateConnecting,
		},
		{
			name:          "Established DTLS connection emits Connected",
			line:          "Established DTLS connection (Server: 1.2.3.4)",
			expectedState: StateConnected,
		},
		{
			name:          "Configured as emits Connected",
			line:          "Configured as 10.10.0.5, with SSL + DTLS and MTU 1400",
			expectedState: StateConnected,
		},
		{
			name:          "Authentication failed emits Error",
			line:          "Authentication failed: Invalid credentials supplied",
			expectedState: StateError,
		},
		{
			name:          "Certificate validation failed emits Error",
			line:          "Certificate validation failed: self signed certificate",
			expectedState: StateError,
		},
		{
			name:          "User cancelled (SIGINT/SIGTERM) emits Disconnecting",
			line:          "User cancelled (SIGINT/SIGTERM); exiting.",
			expectedState: StateDisconnecting,
		},
		{
			name:          "User detached from session emits Disconnecting",
			line:          "User detached from session (SIGHUP); exiting.",
			expectedState: StateDisconnecting,
		},
		{
			name:          "Logout of session completed emits Disconnecting",
			line:          "Logout of session completed.",
			expectedState: StateDisconnecting,
		},
		{
			name:          "CSTP tunnel established emits Connected",
			line:          "[openconnect-worker] CSTP tunnel established and ready.",
			expectedState: StateConnected,
		},
		{
			name:          "Sending BYE packet emits Disconnecting",
			line:          "Sending BYE packet: Disconnected by user",
			expectedState: StateDisconnecting,
		},
		{
			name:          "Worker clean shutdown emits Disconnecting",
			line:          "[openconnect-worker] Logout of session completed (clean shutdown)",
			expectedState: StateDisconnecting,
		},
		{
			name:          "Session terminated emits Disconnecting",
			line:          "Session terminated cleanly by client",
			expectedState: StateDisconnecting,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			sup.ParseLine(tc.line, "stdout")
			mu.Lock()
			ev := lastEvent
			mu.Unlock()

			if ev.State != tc.expectedState {
				t.Errorf("for line %q, expected state %s, got %s", tc.line, tc.expectedState, ev.State)
			}
		})
	}
}

func TestOpenConnect_PasswordNotInCLIArgs(t *testing.T) {
	sup := NewOpenConnectSupervisor("openconnect", nil)

	var capturedArgs []string
	var capturedCmd *exec.Cmd

	sup.SetCmdFactory(func(ctx context.Context, name string, args ...string) *exec.Cmd {
		capturedArgs = args
		capturedCmd = exec.Command("cat")
		return capturedCmd
	})

	secretPassword := "SuperSecretPassword123!"
	cfg := OpenConnectConfig{
		Server:           "vpn.example.com",
		Port:             443,
		Username:         "alice",
		Password:         secretPassword,
		CamouflageSecret: "mysecrettoken",
	}

	ctx := context.Background()
	err := sup.Start(ctx, cfg)
	if err != nil {
		t.Fatalf("sup.Start failed: %v", err)
	}

	// Verify secretPassword is NEVER in capturedArgs
	for _, arg := range capturedArgs {
		if strings.Contains(arg, secretPassword) {
			t.Fatalf("SECURITY VIOLATION: password %q leaked in command line arguments: %v", secretPassword, capturedArgs)
		}
	}

	// Verify --passwd-on-stdin flag is present
	foundPasswdOnStdin := false
	for _, arg := range capturedArgs {
		if arg == "--passwd-on-stdin" {
			foundPasswdOnStdin = true
			break
		}
	}
	if !foundPasswdOnStdin {
		t.Errorf("expected --passwd-on-stdin to be passed to openconnect, args: %v", capturedArgs)
	}

	// Verify camouflage token in URL
	foundCamo := false
	for _, arg := range capturedArgs {
		if strings.Contains(arg, "?mysecrettoken") {
			foundCamo = true
			break
		}
	}
	if !foundCamo {
		t.Errorf("expected camouflage token in target URL, got args: %v", capturedArgs)
	}

	// Clean up
	stopCtx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	_ = sup.Stop(stopCtx)
}

func TestOpenConnect_CleanScriptArgument(t *testing.T) {
	sup := NewOpenConnectSupervisor("openconnect", nil)

	var capturedArgs []string
	sup.SetCmdFactory(func(ctx context.Context, name string, args ...string) *exec.Cmd {
		capturedArgs = args
		return exec.Command("cat")
	})

	cfg := OpenConnectConfig{
		Server: "vpn.example.com",
		Script: `  "C:\Program Files\BobrDobr\bin\vpnc-script-win.js"  `,
	}

	ctx := context.Background()
	if err := sup.Start(ctx, cfg); err != nil {
		t.Fatalf("sup.Start failed: %v", err)
	}
	defer func() {
		stopCtx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()
		_ = sup.Stop(stopCtx)
	}()

	foundScript := false
	for i, arg := range capturedArgs {
		if arg == "--script" && i+1 < len(capturedArgs) {
			foundScript = true
			scriptVal := capturedArgs[i+1]
			expected := `C:\Program Files\BobrDobr\bin\vpnc-script-win.js`
			if scriptVal != expected {
				t.Errorf("expected clean unquoted script path %q, got: %q", expected, scriptVal)
			}
			break
		}
	}

	if !foundScript {
		t.Errorf("expected --script argument in capturedArgs: %v", capturedArgs)
	}
}

func TestOpenConnect_InterfaceAndPhysicalGateway(t *testing.T) {
	sup := NewOpenConnectSupervisor("openconnect", nil)

	var capturedArgs []string
	var capturedEnv []string

	sup.SetCmdFactory(func(ctx context.Context, name string, args ...string) *exec.Cmd {
		capturedArgs = args
		cmd := exec.Command("cat")
		return cmd
	})

	cfg := OpenConnectConfig{
		Server:          "vpn.example.com",
		Port:            443,
		Username:        "bob",
		InterfaceName:   "bobr0",
		PhysicalGateway: "192.168.0.1",
	}

	ctx := context.Background()
	if err := sup.Start(ctx, cfg); err != nil {
		t.Fatalf("sup.Start failed: %v", err)
	}
	defer func() {
		stopCtx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()
		_ = sup.Stop(stopCtx)
	}()

	capturedEnv = sup.cmd.Env

	foundInterface := false
	for i, arg := range capturedArgs {
		if arg == "--interface" && i+1 < len(capturedArgs) && capturedArgs[i+1] == "bobr0" {
			foundInterface = true
			break
		}
	}
	if !foundInterface {
		t.Errorf("expected '--interface bobr0' in capturedArgs: %v", capturedArgs)
	}

	foundGw := false
	for _, e := range capturedEnv {
		if e == "PHYSICAL_GW=192.168.0.1" {
			foundGw = true
			break
		}
	}
	if !foundGw {
		t.Errorf("expected 'PHYSICAL_GW=192.168.0.1' in cmd.Env: %v", capturedEnv)
	}
}

func TestOpenConnect_StartStop_WithMockProcess(t *testing.T) {
	sup := NewOpenConnectSupervisor("openconnect", nil)

	sup.SetCmdFactory(func(ctx context.Context, name string, args ...string) *exec.Cmd {
		return exec.Command("cat")
	})

	var events []Event
	var mu sync.Mutex
	sup.AddListener(func(ev Event) {
		mu.Lock()
		defer mu.Unlock()
		events = append(events, ev)
	})

	cfg := OpenConnectConfig{
		Server: "vpn.example.com",
		Port:   443,
	}

	ctx := context.Background()
	err := sup.Start(ctx, cfg)
	if err != nil {
		t.Fatalf("sup.Start failed: %v", err)
	}

	if !sup.IsRunning() {
		t.Errorf("expected sup.IsRunning() to be true")
	}

	if sup.PID() <= 0 {
		t.Errorf("expected positive PID, got %d", sup.PID())
	}

	stopCtx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	err = sup.Stop(stopCtx)
	if err != nil {
		t.Fatalf("sup.Stop failed: %v", err)
	}

	time.Sleep(100 * time.Millisecond)

	mu.Lock()
	defer mu.Unlock()

	hasConnecting := false
	hasDisconnecting := false
	hasDisconnected := false
	for _, ev := range events {
		if ev.State == StateConnecting {
			hasConnecting = true
		}
		if ev.State == StateDisconnecting {
			hasDisconnecting = true
		}
		if ev.State == StateDisconnected {
			hasDisconnected = true
		}
	}

	if !hasConnecting {
		t.Errorf("expected StateConnecting event to be emitted")
	}
	if !hasDisconnecting {
		t.Errorf("expected StateDisconnecting event to be emitted")
	}
	if !hasDisconnected {
		t.Errorf("expected StateDisconnected event to be emitted")
	}
}

func TestOpenConnectWorker_CLIArgs(t *testing.T) {
	sup := NewOpenConnectSupervisor("openconnect-worker.exe", nil)

	var capturedArgs []string
	sup.SetCmdFactory(func(ctx context.Context, name string, args ...string) *exec.Cmd {
		capturedArgs = args
		return exec.Command("cat")
	})

	cfg := OpenConnectConfig{
		Server:           "vpn.example.com",
		Port:             443,
		Username:         "alice",
		Password:         "supersecret",
		Group:            "kurwa",
		InterfaceName:    "bobr-oc0",
		CamouflageSecret: "kurwa",
		Script:           "some-legacy-script.js",
		Protocol:         "anyconnect",
	}

	ctx := context.Background()
	if err := sup.Start(ctx, cfg); err != nil {
		t.Fatalf("sup.Start failed: %v", err)
	}
	defer func() {
		stopCtx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()
		_ = sup.Stop(stopCtx)
	}()

	// 1. Verify required flags according to Subagent 1 specification
	expectedFlags := []string{
		"--stdin-control",
		"--passwd-on-stdin",
		"--user", "alice",
		"--authgroup", "kurwa",
		"--interface", "bobr-oc0",
	}

	for _, expected := range expectedFlags {
		found := false
		for _, arg := range capturedArgs {
			if arg == expected {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("expected flag %q in worker capturedArgs: %v", expected, capturedArgs)
		}
	}

	// 2. Verify legacy script & protocol flags are NOT present for pure-Go worker
	for _, arg := range capturedArgs {
		if arg == "--script" {
			t.Errorf("forbidden flag --script passed to pure-Go worker: %v", capturedArgs)
		}
		if arg == "--protocol" {
			t.Errorf("forbidden flag --protocol passed to pure-Go worker: %v", capturedArgs)
		}
		if strings.Contains(arg, "supersecret") {
			t.Errorf("password leaked in worker CLI arguments: %v", capturedArgs)
		}
	}

	// 3. Verify camouflage target URL
	lastArg := capturedArgs[len(capturedArgs)-1]
	if !strings.Contains(lastArg, "https://vpn.example.com") || !strings.Contains(lastArg, "?kurwa") {
		t.Errorf("expected target URL with camouflage token, got: %s", lastArg)
	}
}

func TestOpenConnectWorker_StdinLifecycle(t *testing.T) {
	sup := NewOpenConnectSupervisor("openconnect-worker.exe", nil)

	sup.SetCmdFactory(func(ctx context.Context, name string, args ...string) *exec.Cmd {
		return exec.Command("cat")
	})

	cfg := OpenConnectConfig{
		Server:   "vpn.example.com",
		Username: "bob",
		Password: "testpassword",
	}

	ctx := context.Background()
	if err := sup.Start(ctx, cfg); err != nil {
		t.Fatalf("sup.Start failed: %v", err)
	}

	// Verify stdinPipe is kept open while running
	if sup.stdinPipe == nil {
		t.Errorf("expected s.stdinPipe to be held open while running")
	}

	// Stop triggers stdinPipe close and clean process exit
	stopCtx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	if err := sup.Stop(stopCtx); err != nil {
		t.Fatalf("sup.Stop failed: %v", err)
	}

	if sup.stdinPipe != nil {
		t.Errorf("expected s.stdinPipe to be nil after Stop")
	}
}
