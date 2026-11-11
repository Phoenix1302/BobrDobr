//go:build windows

package vpn

// DeliverConsoleSignal is deprecated. In v1.2.3, the pure-Go openconnect-worker
// uses standard input pipe closure (EOF) or native context cancellation instead
// of Win32 console signals. Kept as a no-op for backward compatibility.
func DeliverConsoleSignal(pid int) bool {
	return true
}

// SendGracefulSignal is deprecated. Pure-Go openconnect-worker handles graceful
// AnyConnect CSTP BYE packet termination via standard input pipe closure (EOF / STOP).
// Kept as a no-op for backward compatibility.
func SendGracefulSignal(pid int) bool {
	return true
}
