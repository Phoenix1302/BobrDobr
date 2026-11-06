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
