//go:build !windows

package vpn

// FlushDNSCache is a stub for non-windows platforms.
func FlushDNSCache() {}
