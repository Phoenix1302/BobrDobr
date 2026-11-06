package vpn

import (
	"os/exec"
	"testing"
)

func TestJobObject_CreationAndClose(t *testing.T) {
	job, err := NewJobObject()
	if err != nil {
		t.Fatalf("NewJobObject failed: %v", err)
	}

	cmd := exec.Command("true")
	if err := cmd.Start(); err == nil {
		_ = job.AssignCmd(cmd)
		_ = cmd.Wait()
	}

	if err := job.Close(); err != nil {
		t.Fatalf("job.Close failed: %v", err)
	}
}
