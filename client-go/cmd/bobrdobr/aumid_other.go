//go:build !windows

package main

func SetCurrentProcessExplicitAppUserModelID(aumid string) {}
func ensureAppUserModelIDRegistry()                         {}
func registerBobrDobrProtocol()                             {}
func allowSetForegroundWindow()                             {}
