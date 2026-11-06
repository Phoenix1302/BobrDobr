package singleinstance

import (
	"context"
	"errors"
	"time"
)

const (
	DefaultMutexName = `Global\BobrDobr_VPN_SingleInstance_Unified_v1`
	DefaultPipeName  = `\\.\pipe\BobrDobr_VPN_IPC_v1`
	LowIntegritySDDL = `D:(A;;GA;;;WD)S:(ML;;NW;;;LW)`

	MsgActivate = "ACTIVATE"
	MsgKill     = "KILL"
	MsgPing     = "PING"

	RespPong = "PONG"
	RespOK   = "OK"
)

var (
	ErrAlreadyRunning = errors.New("another instance of BobrDobr is already running")
	ErrNotAcquired    = errors.New("single instance mutex was not acquired")
	ErrTimeout        = errors.New("timeout communicating with single instance pipe")
	ErrInvalidMessage = errors.New("unknown or invalid IPC command")
)

// ProcessInfo represents metadata of an existing BobrDobr process.
type ProcessInfo struct {
	PID         int    `json:"pid"`
	ExeName     string `json:"exe_name"`
	ExePath     string `json:"exe_path"`
	IsInstalled bool   `json:"is_installed"`
}

// MessageHandler is invoked when the IPC server receives a command string.
type MessageHandler func(msg string) (string, error)

// SendMessage sends a message to the single instance IPC pipe with a given timeout.
func (s *SingleInstance) SendMessage(msg string, timeout time.Duration) (string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()
	return SendMessage(ctx, s.pipeName, msg)
}

// TerminateOtherBobrDobrProcesses locates and terminates all other BobrDobr processes.
func TerminateOtherBobrDobrProcesses() error {
	procs, err := FindOtherProcesses()
	if err != nil {
		return err
	}
	for _, p := range procs {
		_ = TerminateProcessByPID(p.PID, 3*time.Second)
	}
	return nil
}
