//go:build windows

package vpn

import (
	"fmt"
	"os/exec"
	"sync"
	"unsafe"

	"golang.org/x/sys/windows"
)

// JobObject wraps a Windows Job Object configured with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE.
// When child processes are assigned to this Job Object, the Windows kernel guarantees
// they are forcibly terminated whenever the parent process exits or terminates.
type JobObject struct {
	mu     sync.Mutex
	handle windows.Handle
}

// NewJobObject creates and configures a Windows Job Object with KILL_ON_JOB_CLOSE.
func NewJobObject() (*JobObject, error) {
	hJob, err := windows.CreateJobObject(nil, nil)
	if err != nil {
		return nil, fmt.Errorf("CreateJobObject failed: %w", err)
	}

	var info windows.JOBOBJECT_EXTENDED_LIMIT_INFORMATION
	info.BasicLimitInformation.LimitFlags = windows.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

	_, err = windows.SetInformationJobObject(
		hJob,
		windows.JobObjectExtendedLimitInformation,
		uintptr(unsafe.Pointer(&info)),
		uint32(unsafe.Sizeof(info)),
	)
	if err != nil {
		_ = windows.CloseHandle(hJob)
		return nil, fmt.Errorf("SetInformationJobObject failed: %w", err)
	}

	return &JobObject{handle: hJob}, nil
}

// AssignProcess assigns a process handle to the job object.
func (j *JobObject) AssignProcess(hProcess windows.Handle) error {
	j.mu.Lock()
	defer j.mu.Unlock()

	if j.handle == 0 {
		return fmt.Errorf("job object is closed")
	}
	return windows.AssignProcessToJobObject(j.handle, hProcess)
}

// AssignProcessPID assigns a process by PID to the job object.
func (j *JobObject) AssignProcessPID(pid int) error {
	if pid <= 0 {
		return fmt.Errorf("invalid pid: %d", pid)
	}

	hProc, err := windows.OpenProcess(
		windows.PROCESS_SET_QUOTA|windows.PROCESS_TERMINATE,
		false,
		uint32(pid),
	)
	if err != nil {
		return fmt.Errorf("OpenProcess failed for PID %d: %w", pid, err)
	}
	defer windows.CloseHandle(hProc)

	return j.AssignProcess(hProc)
}

// AssignCmd assigns an exec.Cmd process to the job object.
func (j *JobObject) AssignCmd(cmd *exec.Cmd) error {
	if cmd == nil || cmd.Process == nil {
		return fmt.Errorf("command or process is nil")
	}
	return j.AssignProcessPID(cmd.Process.Pid)
}

// Close closes the job object handle.
func (j *JobObject) Close() error {
	j.mu.Lock()
	defer j.mu.Unlock()

	if j.handle != 0 {
		err := windows.CloseHandle(j.handle)
		j.handle = 0
		return err
	}
	return nil
}
