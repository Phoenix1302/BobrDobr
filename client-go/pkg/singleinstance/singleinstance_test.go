package singleinstance

import (
	"context"
	"runtime"
	"testing"
	"time"
)

func TestSingleInstance_AcquireAndRelease(t *testing.T) {
	mutexName := "Test_BobrDobr_Mutex_Unified"
	pipeName := "Test_BobrDobr_Pipe_Unified"

	inst1 := New(mutexName, pipeName)
	defer inst1.Close()

	acquired1, err := inst1.TryAcquire()
	if err != nil {
		t.Fatalf("inst1.TryAcquire error: %v", err)
	}
	if !acquired1 {
		t.Fatalf("expected inst1 to acquire mutex, got false")
	}

	// Second instance should fail to acquire
	inst2 := New(mutexName, pipeName)
	defer inst2.Close()

	acquired2, err := inst2.TryAcquire()
	if err != nil {
		t.Fatalf("inst2.TryAcquire error: %v", err)
	}
	if acquired2 {
		t.Fatalf("expected inst2 to NOT acquire mutex while inst1 holds it")
	}

	// Release inst1
	if err := inst1.Release(); err != nil {
		t.Fatalf("inst1.Release error: %v", err)
	}

	// Now inst2 should succeed
	acquired2After, err := inst2.TryAcquire()
	if err != nil {
		t.Fatalf("inst2.TryAcquire error after release: %v", err)
	}
	if !acquired2After {
		t.Fatalf("expected inst2 to acquire mutex after inst1 release")
	}
}

func TestSingleInstance_IPCServer_And_Messages(t *testing.T) {
	pipeName := "Test_BobrDobr_IPC_Server"
	if runtime.GOOS == "windows" {
		pipeName = `\\.\pipe\Test_BobrDobr_IPC_Server_` + time.Now().Format("150405")
	}

	inst := New("Test_Mutex_IPC", pipeName)
	defer inst.Close()

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	activateCalled := false
	killCalled := false

	handler := func(msg string) (string, error) {
		switch msg {
		case MsgActivate:
			activateCalled = true
			return RespOK, nil
		case MsgKill:
			killCalled = true
			return RespOK, nil
		case "CUSTOM":
			return "CUSTOM_RESPONSE", nil
		default:
			return "", ErrInvalidMessage
		}
	}

	if err := inst.StartIPCServer(ctx, handler); err != nil {
		t.Fatalf("StartIPCServer failed: %v", err)
	}
	defer inst.StopIPCServer()

	// Wait a tiny bit for listener to bind
	time.Sleep(50 * time.Millisecond)

	// Test 1: PING -> PONG
	clientCtx, clientCancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer clientCancel()

	resp, err := SendMessage(clientCtx, pipeName, MsgPing)
	if err != nil {
		t.Fatalf("SendMessage PING failed: %v", err)
	}
	if resp != RespPong {
		t.Errorf("expected %s, got %s", RespPong, resp)
	}

	// Test 2: ACTIVATE -> OK
	resp, err = SendMessage(clientCtx, pipeName, MsgActivate)
	if err != nil {
		t.Fatalf("SendMessage ACTIVATE failed: %v", err)
	}
	if resp != RespOK {
		t.Errorf("expected %s, got %s", RespOK, resp)
	}
	if !activateCalled {
		t.Errorf("expected activate handler to be called")
	}

	// Test 3: KILL -> OK
	resp, err = SendMessage(clientCtx, pipeName, MsgKill)
	if err != nil {
		t.Fatalf("SendMessage KILL failed: %v", err)
	}
	if resp != RespOK {
		t.Errorf("expected %s, got %s", RespOK, resp)
	}
	if !killCalled {
		t.Errorf("expected kill handler to be called")
	}

	// Test 4: CUSTOM message
	resp, err = SendMessage(clientCtx, pipeName, "CUSTOM")
	if err != nil {
		t.Fatalf("SendMessage CUSTOM failed: %v", err)
	}
	if resp != "CUSTOM_RESPONSE" {
		t.Errorf("expected CUSTOM_RESPONSE, got %s", resp)
	}
}

func TestSingleInstance_FindOtherProcesses(t *testing.T) {
	// On non-windows, set a mock
	if runtime.GOOS != "windows" {
		SetMockProcesses([]ProcessInfo{
			{
				PID:         1234,
				ExeName:     "bobrdobr.exe",
				ExePath:     "C:\\Users\\User\\AppData\\Local\\Programs\\BobrDobr\\bobrdobr.exe",
				IsInstalled: true,
			},
		})
	}

	procs, err := FindOtherProcesses()
	if err != nil {
		t.Fatalf("FindOtherProcesses failed: %v", err)
	}
	if runtime.GOOS != "windows" {
		if len(procs) != 1 {
			t.Fatalf("expected 1 mock proc, got %d", len(procs))
		}
		if procs[0].PID != 1234 || !procs[0].IsInstalled {
			t.Errorf("unexpected proc info: %+v", procs[0])
		}
	}
}
