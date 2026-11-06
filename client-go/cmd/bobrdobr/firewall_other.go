//go:build !windows

package main

func ensureFirewallRule(ruleName, binPath string) {}
