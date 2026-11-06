package vpn

import (
	"context"
	"os"
	"os/exec"
	"sync"
	"testing"
	"time"
)

func TestAmnezia_ParseLine(t *testing.T) {
	sup := NewAmneziaSupervisor("amneziawg-go", nil)

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
			name:          "Device started emits Connected",
			line:          "2026/11/05 20:00:00 Device started",
			expectedState: StateConnected,
		},
		{
			name:          "Interface created emits Connected",
			line:          "Interface bobr0 created successfully",
			expectedState: StateConnected,
		},
		{
			name:          "Handshake response emits Connected",
			line:          "Receiving handshake response from peer",
			expectedState: StateConnected,
		},
		{
			name:          "Failed to setup wireguard emits Error",
			line:          "Failed to setup wireguard: Timed out waiting for device query",
			expectedState: StateError,
		},
		{
			name:          "Permission denied emits Error",
			line:          "Error: Permission denied opening Wintun adapter",
			expectedState: StateError,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			sup.ParseLine(tc.line, "stdout", "bobr0")
			mu.Lock()
			ev := lastEvent
			mu.Unlock()

			if ev.State != tc.expectedState {
				t.Errorf("for line %q, expected state %s, got %s", tc.line, tc.expectedState, ev.State)
			}
		})
	}
}

func TestAmnezia_StartStop_WithMockProcess(t *testing.T) {
	job, _ := NewJobObject()
	defer job.Close()

	sup := NewAmneziaSupervisor("amneziawg-go", job)

	// Mock command factory using echo / sleep
	sup.SetCmdFactory(func(ctx context.Context, name string, args ...string) *exec.Cmd {
		// Use a script or long-running command that can receive signals
		return exec.Command("sleep", "2")
	})

	var events []Event
	var mu sync.Mutex
	sup.AddListener(func(ev Event) {
		mu.Lock()
		defer mu.Unlock()
		events = append(events, ev)
	})

	cfg := AmneziaConfig{
		ConfigContent: "[Interface]\nPrivateKey = aaaa\nAddress = 10.0.0.2/32\n",
		InterfaceName: "bobr0",
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

	tempConf := sup.tempConfig
	if tempConf == "" {
		t.Errorf("expected tempConfig to be populated")
	} else if _, err := os.Stat(tempConf); os.IsNotExist(err) {
		t.Errorf("expected temp config file to exist on disk: %s", tempConf)
	}

	// Stop the supervisor
	stopCtx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	err = sup.Stop(stopCtx)
	if err != nil {
		t.Fatalf("sup.Stop failed: %v", err)
	}

	// Wait briefly for cleanup goroutine
	time.Sleep(100 * time.Millisecond)

	// Verify temp config was deleted
	if tempConf != "" {
		if _, err := os.Stat(tempConf); !os.IsNotExist(err) {
			t.Errorf("expected temp config file to be removed after Stop, but still exists: %s", tempConf)
		}
	}

	mu.Lock()
	defer mu.Unlock()

	hasConnecting := false
	hasDisconnecting := false
	for _, ev := range events {
		if ev.State == StateConnecting {
			hasConnecting = true
		}
		if ev.State == StateDisconnecting {
			hasDisconnecting = true
		}
	}

	if !hasConnecting {
		t.Errorf("expected StateConnecting event to be emitted")
	}
	if !hasDisconnecting {
		t.Errorf("expected StateDisconnecting event to be emitted")
	}
}
