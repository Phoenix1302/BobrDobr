//go:build !windows

package vpn

import (
	"os"
	"syscall"
)

// SendGracefulSignal sends SIGINT / SIGTERM on non-Windows platforms.
func SendGracefulSignal(pid int) bool {
	if pid <= 0 {
		return false
	}
	proc, err := os.FindProcess(pid)
	if err != nil {
		return false
	}
	return proc.Signal(syscall.SIGINT) == nil
}
