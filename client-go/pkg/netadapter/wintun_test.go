package netadapter

import (
	"context"
	"testing"
	"time"
)

func TestAdapterManager_PingPongRotation(t *testing.T) {
	mgr := NewAdapterManager()
	busyMap := make(map[string]bool)

	mgr.SetCheckBusyFunc(func(name string) bool {
		return busyMap[name]
	})

	// 1st request: defaults to preferred 'bobr0'
	a1 := mgr.NextAdapterName("bobr0")
	if a1 != "bobr0" {
		t.Fatalf("expected bobr0 on first request, got %s", a1)
	}

	// 2nd request: ping-pong rotates to 'bobr1'
	a2 := mgr.NextAdapterName("bobr0")
	if a2 != "bobr1" {
		t.Fatalf("expected bobr1 on second request, got %s", a2)
	}

	// 3rd request: ping-pong rotates back to 'bobr0'
	a3 := mgr.NextAdapterName("bobr0")
	if a3 != "bobr0" {
		t.Fatalf("expected bobr0 on third request, got %s", a3)
	}

	// 4th request: ping-pong rotates to 'bobr1'
	a4 := mgr.NextAdapterName("bobr0")
	if a4 != "bobr1" {
		t.Fatalf("expected bobr1 on fourth request, got %s", a4)
	}
}

func TestAdapterManager_BusyCandidateFallback(t *testing.T) {
	mgr := NewAdapterManager()
	busyMap := make(map[string]bool)

	mgr.SetCheckBusyFunc(func(name string) bool {
		return busyMap[name]
	})

	// 1st request gets bobr0
	a1 := mgr.NextAdapterName("bobr0")
	if a1 != "bobr0" {
		t.Fatalf("expected bobr0, got %s", a1)
	}

	// Suppose bobr1 is currently occupied / tearing down
	busyMap["bobr1"] = true

	// Next request should skip busy bobr1 and choose bobr0
	a2 := mgr.NextAdapterName("bobr0")
	if a2 != "bobr0" {
		t.Fatalf("expected bobr0 when bobr1 is busy, got %s", a2)
	}

	// Suppose BOTH bobr0 and bobr1 are busy
	busyMap["bobr0"] = true
	busyMap["bobr1"] = true

	// Should fall back to bobr2
	a3 := mgr.NextAdapterName("bobr0")
	if a3 != "bobr2" {
		t.Fatalf("expected bobr2 when bobr0 and bobr1 are busy, got %s", a3)
	}
}

func TestIsSafeToClean(t *testing.T) {
	active := []string{"bobr0", "awg2"}

	tests := []struct {
		name     string
		adapter  string
		active   []string
		expected bool
	}{
		{"bobr0 is active", "bobr0", active, false},
		{"bobr1 is inactive bobrdobr", "bobr1", active, true},
		{"awg2 is active", "awg2", active, false},
		{"awg1 is inactive legacy", "awg1", active, true},
		{"Ethernet must never be cleaned", "Ethernet", active, false},
		{"Wi-Fi must never be cleaned", "Wi-Fi", active, false},
		{"Tailscale must never be cleaned", "tailscale0", active, false},
		{"ZeroTier must never be cleaned", "zt0", active, false},
		{"Empty string", "", active, false},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got := IsSafeToClean(tc.adapter, tc.active)
			if got != tc.expected {
				t.Errorf("IsSafeToClean(%q, %v) = %v; want %v", tc.adapter, tc.active, got, tc.expected)
			}
		})
	}
}

func TestCleanupOrphanAdaptersAsync(t *testing.T) {
	// Should run in background without hanging or panicking
	CleanupOrphanAdaptersAsync([]string{"bobr0"}, 500*time.Millisecond)
	time.Sleep(50 * time.Millisecond)
}

func TestFlushDNS_And_Routes_ContextCancellation(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel() // pre-canceled

	_ = FlushDNS(ctx)
	_ = FlushRoutes(ctx, "bobr0")
}

func TestGetAdapterStats(t *testing.T) {
	stats, err := GetAdapterStats("bobr0")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if stats.RxBytes != 0 || stats.TxBytes != 0 {
		t.Fatalf("expected 0 stats by default, got rx=%d, tx=%d", stats.RxBytes, stats.TxBytes)
	}

	SetMockAdapterStats("bobr0", AdapterStats{
		RxBytes: 1234567,
		TxBytes: 7654321,
	})
	defer SetMockAdapterStats("bobr0", AdapterStats{})

	stats2, err := GetAdapterStats("bobr0")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if stats2.RxBytes != 1234567 || stats2.TxBytes != 7654321 {
		t.Fatalf("expected mocked stats, got rx=%d, tx=%d", stats2.RxBytes, stats2.TxBytes)
	}
}

func TestFormatSpeed(t *testing.T) {
	tests := []struct {
		bytesPerSec uint64
		expected    string
	}{
		{0, "0 КБ/с"},
		{500, "500 Б/с"},
		{1024, "1 КБ/с"},
		{350 * 1024, "350 КБ/с"},
		{1258291, "1.2 МБ/с"},            // ~1.2 MB/s
		{2684354560, "2.5 ГБ/с"},         // 2.5 GB/s
	}

	for _, tc := range tests {
		got := FormatSpeed(tc.bytesPerSec)
		if got != tc.expected {
			t.Errorf("FormatSpeed(%d) = %q, want %q", tc.bytesPerSec, got, tc.expected)
		}
	}
}

func TestFormatMB(t *testing.T) {
	tests := []struct {
		bytes    uint64
		expected string
	}{
		{0, "0.0"},
		{524288, "0.5"},
		{1048576, "1.0"},
		{13000000, "12.4"},
	}

	for _, tc := range tests {
		got := FormatMB(tc.bytes)
		if got != tc.expected {
			t.Errorf("FormatMB(%d) = %q, want %q", tc.bytes, got, tc.expected)
		}
	}
}
