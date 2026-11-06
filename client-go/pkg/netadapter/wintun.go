package netadapter

import (
	"context"
	"fmt"
	"strconv"
	"strings"
	"sync"
	"time"
)

// OrphanAdapter represents a lingering or orphaned network adapter discovered on the system.
type OrphanAdapter struct {
	InstanceID    string `json:"instance_id"`
	InterfaceName string `json:"interface_name"`
	Description   string `json:"description"`
}

// AdapterManager handles ping-pong adapter rotation between bobr0 and bobr1
// to eliminate Wintun device teardown race conditions.
type AdapterManager struct {
	mu           sync.Mutex
	lastAssigned string
	checkBusy    func(string) bool
}

// NewAdapterManager creates a new AdapterManager.
func NewAdapterManager() *AdapterManager {
	m := &AdapterManager{}
	m.checkBusy = m.defaultIsBusy
	return m
}

// SetCheckBusyFunc allows injecting a custom busy check function (useful for testing).
func (m *AdapterManager) SetCheckBusyFunc(fn func(string) bool) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if fn != nil {
		m.checkBusy = fn
	} else {
		m.checkBusy = m.defaultIsBusy
	}
}

// Reset clears the rotation history.
func (m *AdapterManager) Reset() {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.lastAssigned = ""
}

// LastAssigned returns the most recently assigned adapter name.
func (m *AdapterManager) LastAssigned() string {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.lastAssigned
}

// NextAdapterName implements ping-pong rotation between bobr0 and bobr1.
// If the preferred or rotated adapter is currently busy or lingering in teardown,
// it smoothly falls back to an available candidate (e.g. bobr1, bobr0, bobr2...).
func (m *AdapterManager) NextAdapterName(preferred string) string {
	m.mu.Lock()
	defer m.mu.Unlock()

	targetPref := strings.TrimSpace(preferred)
	if targetPref == "" {
		targetPref = "bobr0"
	}

	prefix := extractPrefix(targetPref)
	if prefix == "" {
		prefix = "bobr"
	}

	var candidates []string

	if m.lastAssigned != "" && strings.HasPrefix(m.lastAssigned, prefix) {
		lastIdx := extractIndex(m.lastAssigned)
		var order []int
		if lastIdx == 0 {
			order = append([]int{1, 0}, sequence(2, 9)...)
		} else if lastIdx == 1 {
			order = append([]int{0, 1}, sequence(2, 9)...)
		} else {
			order = append([]int{0, 1}, sequenceExcept(2, 9, lastIdx)...)
			order = append(order, lastIdx)
		}
		for _, idx := range order {
			candidates = append(candidates, fmt.Sprintf("%s%d", prefix, idx))
		}
	} else {
		prefIdx := extractIndex(targetPref)
		var order []int
		if prefIdx == 0 {
			order = append([]int{0, 1}, sequence(2, 9)...)
		} else if prefIdx == 1 {
			order = append([]int{1, 0}, sequence(2, 9)...)
		} else {
			order = append([]int{prefIdx, 0, 1}, sequenceExcept(2, 9, prefIdx)...)
		}
		for _, idx := range order {
			candidates = append(candidates, fmt.Sprintf("%s%d", prefix, idx))
		}
	}

	seen := make(map[string]bool)
	var orderedCandidates []string
	for _, c := range candidates {
		if !seen[c] {
			seen[c] = true
			orderedCandidates = append(orderedCandidates, c)
		}
	}

	for _, cand := range orderedCandidates {
		if !m.checkBusy(cand) {
			m.lastAssigned = cand
			return cand
		}
	}

	fallback := orderedCandidates[0]
	m.lastAssigned = fallback
	return fallback
}

func extractPrefix(s string) string {
	return strings.TrimRight(s, "0123456789")
}

func extractIndex(s string) int {
	prefix := extractPrefix(s)
	numStr := strings.TrimPrefix(s, prefix)
	idx, err := strconv.Atoi(numStr)
	if err != nil {
		return 0
	}
	return idx
}

func sequence(start, end int) []int {
	var res []int
	for i := start; i <= end; i++ {
		res = append(res, i)
	}
	return res
}

func sequenceExcept(start, end, skip int) []int {
	var res []int
	for i := start; i <= end; i++ {
		if i != skip {
			res = append(res, i)
		}
	}
	return res
}

func (m *AdapterManager) defaultIsBusy(name string) bool {
	return IsAdapterBusy(name)
}

// IsSafeToClean checks if an adapter name is an internal BobrDobr tunnel ('bobr*' or legacy 'awg*')
// and is not part of the activeInterfaces whitelist.
// NEVER returns true for Ethernet, Wi-Fi, Tailscale, ZeroTier, or active tunnels.
func IsSafeToClean(adapterName string, activeInterfaces []string) bool {
	name := strings.ToLower(strings.TrimSpace(adapterName))
	if name == "" {
		return false
	}

	// Strictly permit only bobr* and awg*
	if !strings.HasPrefix(name, "bobr") && !strings.HasPrefix(name, "awg") {
		return false
	}

	for _, active := range activeInterfaces {
		if strings.ToLower(strings.TrimSpace(active)) == name {
			return false
		}
	}

	return true
}

// CleanupOrphanAdaptersAsync executes orphan adapter cleanup in a background goroutine.
func CleanupOrphanAdaptersAsync(activeInterfaces []string, timeout time.Duration) {
	go func() {
		ctx, cancel := context.WithTimeout(context.Background(), timeout)
		defer cancel()
		_ = CleanupOrphanAdapters(ctx, activeInterfaces)
	}()
}

// FormatSpeed formats a byte rate into a human-readable string (e.g. "1.2 МБ/с", "350 КБ/с").
func FormatSpeed(bytesPerSec uint64) string {
	const (
		kb = 1024
		mb = 1024 * 1024
		gb = 1024 * 1024 * 1024
	)
	if bytesPerSec >= gb {
		return fmt.Sprintf("%.1f ГБ/с", float64(bytesPerSec)/float64(gb))
	}
	if bytesPerSec >= mb {
		return fmt.Sprintf("%.1f МБ/с", float64(bytesPerSec)/float64(mb))
	}
	if bytesPerSec >= kb {
		return fmt.Sprintf("%d КБ/с", bytesPerSec/kb)
	}
	if bytesPerSec > 0 {
		return fmt.Sprintf("%d Б/с", bytesPerSec)
	}
	return "0 КБ/с"
}

// FormatMB formats a byte count into megabytes string (e.g. "12.4", "0.0").
func FormatMB(bytes uint64) string {
	return fmt.Sprintf("%.1f", float64(bytes)/(1024*1024))
}

