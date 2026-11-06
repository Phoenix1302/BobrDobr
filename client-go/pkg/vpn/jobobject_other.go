//go:build !windows

package vpn

import "os/exec"

// JobObject stub for non-Windows platforms.
type JobObject struct{}

// NewJobObject creates a stub JobObject.
func NewJobObject() (*JobObject, error) {
	return &JobObject{}, nil
}

// AssignProcess stub.
func (j *JobObject) AssignProcess(handle uintptr) error {
	return nil
}

// AssignProcessPID stub.
func (j *JobObject) AssignProcessPID(pid int) error {
	return nil
}

// AssignCmd stub.
func (j *JobObject) AssignCmd(cmd *exec.Cmd) error {
	return nil
}

// Close stub.
func (j *JobObject) Close() error {
	return nil
}
