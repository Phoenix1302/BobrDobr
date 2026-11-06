//go:build windows

package main

import (
	"fmt"
	"log"
	"os"
	"os/exec"

	"golang.org/x/sys/windows"
)

// ensureFirewallRule ensures inbound traffic is allowed through Windows Defender Firewall for the specified executable
func ensureFirewallRule(ruleName, binPath string) {
	if binPath == "" {
		return
	}
	if _, err := os.Stat(binPath); err != nil {
		return
	}

	// Delete any previous rule with this name to prevent duplicate rules in Windows Firewall
	delCmd := exec.Command("netsh", "advfirewall", "firewall", "delete", "rule", fmt.Sprintf("name=%s", ruleName))
	delCmd.SysProcAttr = &windows.SysProcAttr{
		HideWindow:    true,
		CreationFlags: windows.CREATE_NO_WINDOW,
	}
	_ = delCmd.Run()

	// Add new inbound allow rule
	addCmd := exec.Command("netsh", "advfirewall", "firewall", "add", "rule",
		fmt.Sprintf("name=%s", ruleName),
		"dir=in",
		"action=allow",
		fmt.Sprintf("program=%s", binPath),
		"enable=yes",
	)
	addCmd.SysProcAttr = &windows.SysProcAttr{
		HideWindow:    true,
		CreationFlags: windows.CREATE_NO_WINDOW,
	}
	if err := addCmd.Run(); err != nil {
		log.Printf("[БРАНДМАУЭР] Ошибка добавления правила '%s': %v", ruleName, err)
	} else {
		log.Printf("[БРАНДМАУЭР] Правило '%s' успешно добавлено для %s", ruleName, binPath)
	}
}
