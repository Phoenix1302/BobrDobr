//go:build !windows

package netadapter

import (
	"context"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
)

var (
	mockOrphansMu sync.RWMutex
	mockOrphans   []OrphanAdapter

	mockStatsMu sync.RWMutex
	mockStats   = make(map[string]AdapterStats)
)

// AdapterStats represents network telemetry for an adapter.
type AdapterStats struct {
	RxBytes uint64 `json:"rx_bytes"`
	TxBytes uint64 `json:"tx_bytes"`
}

// SetMockAdapterStats sets mock adapter stats for testing.
func SetMockAdapterStats(name string, stats AdapterStats) {
	mockStatsMu.Lock()
	defer mockStatsMu.Unlock()
	mockStats[name] = stats
}

// GetAdapterStats returns a stub AdapterStats for non-Windows platforms.
func GetAdapterStats(name string) (AdapterStats, error) {
	mockStatsMu.RLock()
	defer mockStatsMu.RUnlock()
	if s, ok := mockStats[name]; ok {
		return s, nil
	}
	return AdapterStats{}, nil
}

// SetMockOrphans sets a mock list of orphaned adapters for unit testing.
func SetMockOrphans(orphans []OrphanAdapter) {
	mockOrphansMu.Lock()
	defer mockOrphansMu.Unlock()
	mockOrphans = orphans
}

// IsAdapterPresent checks if the interface exists on the host.
func IsAdapterPresent(name string) bool {
	if strings.TrimSpace(name) == "" {
		return false
	}
	_, err := net.InterfaceByName(name)
	if err == nil {
		return true
	}
	// Fallback to /sys/class/net
	_, err = os.Stat(filepath.Join("/sys/class/net", name))
	return err == nil
}

// IsAdapterBusy checks if the interface exists or is active.
func IsAdapterBusy(name string) bool {
	return IsAdapterPresent(name)
}

// ScanOrphanAdapters returns detected or mocked orphan adapters.
func ScanOrphanAdapters() ([]OrphanAdapter, error) {
	mockOrphansMu.RLock()
	if len(mockOrphans) > 0 {
		defer mockOrphansMu.RUnlock()
		return mockOrphans, nil
	}
	mockOrphansMu.RUnlock()

	ifaces, err := net.Interfaces()
	if err != nil {
		return nil, nil
	}

	var results []OrphanAdapter
	for _, iface := range ifaces {
		name := strings.ToLower(iface.Name)
		if strings.HasPrefix(name, "bobr") || strings.HasPrefix(name, "awg") {
			results = append(results, OrphanAdapter{
				InstanceID:    iface.Name,
				InterfaceName: iface.Name,
				Description:   "Tunnel Interface",
			})
		}
	}
	return results, nil
}

// CleanupOrphanAdapters cleans up lingering test/orphan interfaces.
func CleanupOrphanAdapters(ctx context.Context, activeInterfaces []string) error {
	orphans, err := ScanOrphanAdapters()
	if err != nil {
		return err
	}

	for _, o := range orphans {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		if IsSafeToClean(o.InterfaceName, activeInterfaces) {
			_ = DeleteAdapter(ctx, o.InterfaceName)
		}
	}
	return nil
}

// DeleteAdapter deletes a tunnel interface using ip link delete if available.
func DeleteAdapter(ctx context.Context, interfaceName string) error {
	name := strings.TrimSpace(interfaceName)
	if name == "" {
		return nil
	}
	cmd := exec.CommandContext(ctx, "ip", "link", "delete", name)
	return cmd.Run()
}

// FlushDNS flushes local DNS resolver cache if available.
func FlushDNS(ctx context.Context) error {
	if _, err := exec.LookPath("resolvectl"); err == nil {
		return exec.CommandContext(ctx, "resolvectl", "flush-caches").Run()
	}
	if _, err := exec.LookPath("systemd-resolve"); err == nil {
		return exec.CommandContext(ctx, "systemd-resolve", "--flush-caches").Run()
	}
	return nil
}

// FlushRoutes flushes routes on the interface if available.
func FlushRoutes(ctx context.Context, interfaceName string) error {
	name := strings.TrimSpace(interfaceName)
	if name == "" {
		return nil
	}
	if _, err := exec.LookPath("ip"); err == nil {
		return exec.CommandContext(ctx, "ip", "route", "flush", "dev", name).Run()
	}
	return nil
}
