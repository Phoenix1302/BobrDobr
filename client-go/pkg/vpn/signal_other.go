//go:build !windows

package vpn

// DeliverConsoleSignal is deprecated. Kept as a no-op for backward compatibility.
func DeliverConsoleSignal(pid int) bool {
	return false
}

// SendGracefulSignal is deprecated. Pure-Go openconnect-worker handles graceful
// AnyConnect CSTP BYE packet termination via standard input pipe closure (EOF / STOP).
// Kept as a no-op for backward compatibility.
func SendGracefulSignal(pid int) bool {
	return true
}
