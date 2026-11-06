//go:build !windows

package config

import "errors"

// ErrDPAPINotSupported is returned when DPAPI operations are attempted on non-Windows platforms.
var ErrDPAPINotSupported = errors.New("DPAPI is only supported on Windows")

func dpapiProtect(data []byte) ([]byte, error) {
	return nil, ErrDPAPINotSupported
}

func dpapiUnprotect(data []byte) ([]byte, error) {
	return nil, ErrDPAPINotSupported
}
