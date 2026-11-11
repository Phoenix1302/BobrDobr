package vpn

import (
	"context"
	"net"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
)

func TestParseBypassExceptions(t *testing.T) {
	input := `
# Header comment
192.168.1.0/24 # internal LAN
10.0.0.0/8 ; corporate network

// Russian government portals
gosuslugi.ru
nalog.gov.ru

# Single IP bypass
1.1.1.1
8.8.8.8:53 // with port

# Duplicate entry
1.1.1.1
gosuslugi.ru

   # Blank lines with whitespace   
   
172.16.0.0/12
`

	entries, err := ParseBypassExceptions(strings.NewReader(input))
	if err != nil {
		t.Fatalf("ParseBypassExceptions failed: %v", err)
	}

	expected := []string{
		"192.168.1.0/24",
		"10.0.0.0/8",
		"gosuslugi.ru",
		"nalog.gov.ru",
		"1.1.1.1",
		"8.8.8.8:53",
		"172.16.0.0/12",
	}

	if len(entries) != len(expected) {
		t.Fatalf("Expected %d entries, got %d: %v", len(expected), len(entries), entries)
	}

	for i, exp := range expected {
		if entries[i] != exp {
			t.Errorf("At index %d: expected %q, got %q", i, exp, entries[i])
		}
	}
}

func TestParseBypassExceptionsFile(t *testing.T) {
	tempDir, err := os.MkdirTemp("", "bobrdobr-route-test-*")
	if err != nil {
		t.Fatalf("Failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tempDir)

	filePath := filepath.Join(tempDir, "bypass.txt")
	content := "# Custom bypass\n203.0.113.0/24\nyoutube.com\n"
	if err := os.WriteFile(filePath, []byte(content), 0644); err != nil {
		t.Fatalf("Failed to write test file: %v", err)
	}

	entries, err := ParseBypassExceptionsFile(filePath)
	if err != nil {
		t.Fatalf("ParseBypassExceptionsFile failed: %v", err)
	}

	if len(entries) != 2 || entries[0] != "203.0.113.0/24" || entries[1] != "youtube.com" {
		t.Fatalf("Unexpected entries: %v", entries)
	}
}

func TestRouteManager_ApplyAndClearBypassRoutes(t *testing.T) {
	rm := NewRouteManager()
	rm.SetCachedGateway("192.168.1.1")

	var executedCmds [][]string
	var mu sync.Mutex

	rm.SetRouteExecutor(func(args ...string) error {
		mu.Lock()
		defer mu.Unlock()
		executedCmds = append(executedCmds, args)
		return nil
	})

	// Mock DNS resolver
	rm.SetResolver(func(ctx context.Context, host string) ([]net.IP, error) {
		if host == "gosuslugi.ru" {
			return []net.IP{net.ParseIP("109.207.2.146"), net.ParseIP("109.207.2.147")}, nil
		}
		if host == "youtube.com" {
			return []net.IP{net.ParseIP("142.250.180.206")}, nil
		}
		return nil, nil
	})

	entries := []string{
		"192.168.100.0/24", // CIDR
		"8.8.8.8",          // Single IP
		"gosuslugi.ru",     // Domain resolving to 2 IPs
		"youtube.com",      // Domain resolving to 1 IP
	}

	added, err := rm.ApplyBypassRoutes(entries)
	if err != nil {
		t.Fatalf("ApplyBypassRoutes failed: %v", err)
	}

	// Total routes: 1 (CIDR) + 1 (single IP) + 2 (gosuslugi) + 1 (youtube) = 5
	if added != 5 {
		t.Fatalf("Expected 5 routes added, got %d", added)
	}

	active := rm.GetActiveRoutes()
	if len(active) != 5 {
		t.Fatalf("Expected 5 active routes, got %d", len(active))
	}

	// Verify all executed commands used "add", correct mask, gateway 192.168.1.1, and metric 1
	mu.Lock()
	cmds := executedCmds
	mu.Unlock()

	for _, cmd := range cmds {
		if cmd[0] != "add" {
			t.Errorf("Expected 'add', got %v", cmd)
		}
		// Expect: add <dest> mask <mask> 192.168.1.1 metric 1
		if cmd[4] != "192.168.1.1" {
			t.Errorf("Expected gateway 192.168.1.1, got %s in %v", cmd[4], cmd)
		}
		if cmd[5] != "metric" || cmd[6] != "1" {
			t.Errorf("Expected metric 1, got %v", cmd)
		}
	}

	// Now verify Clean deletion on disconnect
	executedCmds = nil
	cleared := rm.ClearBypassRoutes()
	if cleared != 5 {
		t.Fatalf("Expected 5 cleared routes, got %d", cleared)
	}

	if len(rm.GetActiveRoutes()) != 0 {
		t.Fatalf("Expected 0 active routes after ClearBypassRoutes, got %d", len(rm.GetActiveRoutes()))
	}

	mu.Lock()
	deleteCmds := executedCmds
	mu.Unlock()

	if len(deleteCmds) != 5 {
		t.Fatalf("Expected 5 delete commands, got %d", len(deleteCmds))
	}
	for _, cmd := range deleteCmds {
		if cmd[0] != "delete" {
			t.Errorf("Expected 'delete', got %v", cmd)
		}
	}
}

func TestParseDefaultGatewayFromRoutePrint(t *testing.T) {
	sampleOutput := `
===========================================================================
Active Routes:
Network Destination        Netmask          Gateway       Interface  Metric
          0.0.0.0          0.0.0.0      192.168.0.1     192.168.1.31     25
          0.0.0.0          0.0.0.0         On-link          10.8.0.2      0
        127.0.0.0        255.0.0.0         On-link         127.0.0.1    331
===========================================================================
`
	gw, err := parseDefaultGatewayFromRoutePrint(sampleOutput)
	if err != nil {
		t.Fatalf("parseDefaultGatewayFromRoutePrint failed: %v", err)
	}

	if gw != "192.168.0.1" {
		t.Fatalf("Expected 192.168.0.1, got %q", gw)
	}
}

func TestRouteManager_ApplyBypassRoutes_WithInterfaceIndex(t *testing.T) {
	rm := NewRouteManager()
	rm.SetCachedGateway("192.168.1.1")
	rm.SetCachedInterfaceIndex(25)

	var executedCmds [][]string
	rm.SetRouteExecutor(func(args ...string) error {
		executedCmds = append(executedCmds, args)
		return nil
	})

	entries := []string{"8.8.8.8"}
	added, err := rm.ApplyBypassRoutes(entries)
	if err != nil {
		t.Fatalf("ApplyBypassRoutes failed: %v", err)
	}
	if added != 1 {
		t.Fatalf("Expected 1 route added, got %d", added)
	}

	if len(executedCmds) != 1 {
		t.Fatalf("Expected 1 command executed, got %d", len(executedCmds))
	}

	cmd := executedCmds[0]
	// Expected: add 8.8.8.8 mask 255.255.255.255 192.168.1.1 metric 1 if 25
	expected := []string{"add", "8.8.8.8", "mask", "255.255.255.255", "192.168.1.1", "metric", "1", "if", "25"}
	if len(cmd) != len(expected) {
		t.Fatalf("Expected %d arguments, got %d: %v", len(expected), len(cmd), cmd)
	}
	for i, exp := range expected {
		if cmd[i] != exp {
			t.Errorf("At index %d: expected %q, got %q", i, exp, cmd[i])
		}
	}

	active := rm.GetActiveRoutes()
	if len(active) != 1 || active[0].InterfaceIndex != 25 {
		t.Fatalf("Expected active route with interface index 25, got: %+v", active)
	}
}

func TestRouteManager_DetectPhysicalGateway_WithInterfaceFinder(t *testing.T) {
	rm := NewRouteManager()

	sampleOutput := `
===========================================================================
Active Routes:
Network Destination        Netmask          Gateway       Interface  Metric
          0.0.0.0          0.0.0.0      192.168.0.1     192.168.1.31     25
===========================================================================
`
	rm.SetCmdRunner(func(name string, args ...string) (string, error) {
		if name == "route" {
			return sampleOutput, nil
		}
		return "", nil
	})

	rm.SetInterfaceFinder(func(targetIP string) int {
		if targetIP == "192.168.1.31" {
			return 25
		}
		return 0
	})

	gw, err := rm.DetectPhysicalGateway()
	if err != nil {
		t.Fatalf("DetectPhysicalGateway failed: %v", err)
	}
	if gw != "192.168.0.1" {
		t.Fatalf("Expected gw 192.168.0.1, got %s", gw)
	}
	if rm.CachedInterfaceIndex() != 25 {
		t.Fatalf("Expected ifIndex 25, got %d", rm.CachedInterfaceIndex())
	}
}

