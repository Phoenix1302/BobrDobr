package vpn

import (
	"context"
	"errors"
	"math/big"
	"net"
	"strings"
	"testing"
)

// Helper to calculate total IPv4 addresses covered by a list of CIDRs
func totalIPAddresses(cidrs []*net.IPNet) *big.Int {
	total := big.NewInt(0)
	two := big.NewInt(2)
	for _, c := range cidrs {
		ones, bits := c.Mask.Size()
		if bits == 32 {
			count := new(big.Int).Exp(two, big.NewInt(int64(32-ones)), nil)
			total.Add(total, count)
		}
	}
	return total
}

func parseNet(s string) *net.IPNet {
	_, ipNet, err := net.ParseCIDR(s)
	if err != nil {
		panic(err)
	}
	return ipNet
}

func TestSubtractCIDRs_SingleExclude(t *testing.T) {
	base := parseNet("0.0.0.0/0")
	exclude := parseNet("10.0.0.0/8")

	res := SubtractCIDRs(base, []*net.IPNet{exclude})

	// Total IPv4 addresses is 2^32 = 4294967296
	// 10.0.0.0/8 has 2^24 = 16777216 addresses
	// Result must cover exactly 2^32 - 2^24 = 4278190080 addresses
	total := totalIPAddresses(res)
	expectedTotal := new(big.Int).Sub(
		new(big.Int).Exp(big.NewInt(2), big.NewInt(32), nil),
		new(big.Int).Exp(big.NewInt(2), big.NewInt(24), nil),
	)

	if total.Cmp(expectedTotal) != 0 {
		t.Fatalf("Expected total IPs %s, got %s", expectedTotal.String(), total.String())
	}

	// Verify that 10.x.x.x is NEVER contained in any of the returned CIDRs
	for _, c := range res {
		if c.Contains(net.ParseIP("10.0.0.1")) || c.Contains(net.ParseIP("10.255.255.255")) {
			t.Fatalf("Excluded IP 10.x.x.x was found in returned CIDR: %s", c.String())
		}
	}

	// Verify that outside IPs ARE contained in exactly one returned CIDR
	testIPs := []string{"1.1.1.1", "8.8.8.8", "192.168.1.1", "220.0.0.1"}
	for _, ipStr := range testIPs {
		ip := net.ParseIP(ipStr)
		matchCount := 0
		for _, c := range res {
			if c.Contains(ip) {
				matchCount++
			}
		}
		if matchCount != 1 {
			t.Fatalf("IP %s matched %d CIDRs, expected exactly 1", ipStr, matchCount)
		}
	}
}

func TestSubtractCIDRs_SingleHost(t *testing.T) {
	base := parseNet("0.0.0.0/0")
	exclude := parseNet("1.1.1.1/32")

	res := SubtractCIDRs(base, []*net.IPNet{exclude})

	// Subtracting /32 produces 32 CIDR blocks
	if len(res) != 32 {
		t.Fatalf("Expected 32 CIDR blocks, got %d", len(res))
	}

	total := totalIPAddresses(res)
	expectedTotal := new(big.Int).Sub(
		new(big.Int).Exp(big.NewInt(2), big.NewInt(32), nil),
		big.NewInt(1),
	)

	if total.Cmp(expectedTotal) != 0 {
		t.Fatalf("Expected total IPs %s, got %s", expectedTotal.String(), total.String())
	}

	// 1.1.1.1 must not be in any returned CIDR
	target := net.ParseIP("1.1.1.1")
	for _, c := range res {
		if c.Contains(target) {
			t.Fatalf("Excluded host 1.1.1.1 found in CIDR %s", c.String())
		}
	}

	// Neighbor 1.1.1.0 and 1.1.1.2 must be present
	for _, neighborStr := range []string{"1.1.1.0", "1.1.1.2"} {
		ip := net.ParseIP(neighborStr)
		found := false
		for _, c := range res {
			if c.Contains(ip) {
				found = true
				break
			}
		}
		if !found {
			t.Fatalf("Neighbor IP %s was missing from results", neighborStr)
		}
	}
}

func TestSubtractCIDRs_CoverEntireBase(t *testing.T) {
	base := parseNet("192.168.1.0/24")
	exclude := parseNet("192.168.0.0/16") // Exclude is larger than base

	res := SubtractCIDRs(base, []*net.IPNet{exclude})
	if len(res) != 0 {
		t.Fatalf("Expected 0 CIDRs when exclude covers base, got %d", len(res))
	}
}

func TestSubtractCIDRs_NoOverlap(t *testing.T) {
	base := parseNet("192.168.1.0/24")
	exclude := parseNet("10.0.0.0/8")

	res := SubtractCIDRs(base, []*net.IPNet{exclude})
	if len(res) != 1 || res[0].String() != "192.168.1.0/24" {
		t.Fatalf("Expected unchanged base CIDR, got: %v", res)
	}
}

func TestCalculateAllowedIPsForBypass(t *testing.T) {
	orig := "0.0.0.0/0, ::/0"
	bypass := []string{
		"# Comment line",
		"192.168.1.0/24",
		"8.8.8.8",
		"gosuslugi.ru",
	}

	mockResolver := func(ctx context.Context, host string) ([]net.IP, error) {
		if host == "gosuslugi.ru" {
			return []net.IP{net.ParseIP("109.207.2.146")}, nil
		}
		return nil, nil
	}

	res, err := CalculateAllowedIPsForBypass(orig, bypass, mockResolver)
	if err != nil {
		t.Fatalf("CalculateAllowedIPsForBypass failed: %v", err)
	}

	// Ensure IPv6 ::/0 is preserved at the end
	if !strings.HasSuffix(res, "::/0") {
		t.Fatalf("Expected ::/0 to be preserved in %q", res)
	}

	// Verify that excluded IPs are not in any of the returned CIDRs
	items := strings.Split(res, ",")
	var cidrs []*net.IPNet
	for _, it := range items {
		it = strings.TrimSpace(it)
		if it == "::/0" {
			continue
		}
		_, c, err := net.ParseCIDR(it)
		if err != nil {
			t.Fatalf("Invalid CIDR in output: %s (%v)", it, err)
		}
		cidrs = append(cidrs, c)
	}

	excludedIPs := []string{
		"192.168.1.1",
		"192.168.1.254",
		"8.8.8.8",
		"109.207.2.146",
	}
	for _, exc := range excludedIPs {
		ip := net.ParseIP(exc)
		for _, c := range cidrs {
			if c.Contains(ip) {
				t.Fatalf("Excluded IP %s was covered by returned CIDR %s", exc, c.String())
			}
		}
	}

	// Verify that non-excluded IPs ARE covered
	allowedIPs := []string{
		"1.1.1.1",
		"8.8.4.4",
		"192.168.2.1",
		"109.207.2.145",
	}
	for _, allow := range allowedIPs {
		ip := net.ParseIP(allow)
		found := false
		for _, c := range cidrs {
			if c.Contains(ip) {
				found = true
				break
			}
		}
		if !found {
			t.Fatalf("Allowed IP %s was missing from results", allow)
		}
	}
}

func TestReplaceAllowedIPsInConfig(t *testing.T) {
	inputConf := `[Interface]
Address = 10.8.0.2/24
PrivateKey = key123=
DNS = 1.1.1.1

[Peer]
PublicKey = peer456=
Endpoint = 1.2.3.4:51820
AllowedIPs = 0.0.0.0/0, ::/0
PersistentKeepalive = 25
`

	newAllowed := "0.0.0.0/1, 128.0.0.0/1, ::/0"
	extracted := ExtractAllowedIPsFromConfig(inputConf)
	if extracted != "0.0.0.0/0, ::/0" {
		t.Fatalf("ExtractAllowedIPsFromConfig got %q, expected '0.0.0.0/0, ::/0'", extracted)
	}

	replaced := ReplaceAllowedIPsInConfig(inputConf, newAllowed)
	if !strings.Contains(replaced, "AllowedIPs = 0.0.0.0/1, 128.0.0.0/1, ::/0") {
		t.Fatalf("ReplaceAllowedIPsInConfig did not replace AllowedIPs properly:\n%s", replaced)
	}

	// Verify other fields remain intact
	if !strings.Contains(replaced, "Address = 10.8.0.2/24") || !strings.Contains(replaced, "PersistentKeepalive = 25") {
		t.Fatalf("Config corrupted during replacement:\n%s", replaced)
	}
}

func TestPreResolveBypassEntries(t *testing.T) {
	flushCalled := false
	mockFlush := func() {
		flushCalled = true
	}

	mockResolver := func(ctx context.Context, network, host string) ([]net.IP, error) {
		if network != "ip4" {
			t.Fatalf("expected network ip4, got %s", network)
		}
		switch host {
		case "gosuslugi.ru":
			return []net.IP{net.ParseIP("109.207.2.146")}, nil
		case "multi-ip.example.com":
			return []net.IP{net.ParseIP("1.2.3.4"), net.ParseIP("1.2.3.5")}, nil
		case "duplicate-ip.example.com":
			return []net.IP{net.ParseIP("8.8.8.8")}, nil
		case "unresolvable.example.com":
			return nil, errors.New("NXDOMAIN")
		case "no-ipv4.example.com":
			return []net.IP{net.ParseIP("2001:db8::1")}, nil
		default:
			return nil, errors.New("unknown host")
		}
	}

	input := []string{
		"# Comment line 1",
		"  // Comment line 2",
		"; Comment line 3",
		"",
		"   ",
		"192.168.1.0/24",
		" 192.168.1.0/24 ",         // Duplicate CIDR
		"8.8.8.8",
		"8.8.8.8",                 // Duplicate IP
		"10.0.0.1:8080",           // Host:Port IP
		"gosuslugi.ru",
		"multi-ip.example.com:443", // Host:Port domain
		"duplicate-ip.example.com", // Resolves to 8.8.8.8 (already seen)
		"unresolvable.example.com", // Fails resolution -> fallback
		"no-ipv4.example.com",      // No IPv4 -> fallback
	}

	result := preResolveBypassEntriesWithResolver(input, mockFlush, mockResolver)

	if !flushCalled {
		t.Fatal("expected FlushDNSCache to be called")
	}

	expected := []string{
		"192.168.1.0/24",
		"8.8.8.8",
		"10.0.0.1",
		"109.207.2.146",
		"1.2.3.4",
		"1.2.3.5",
		"unresolvable.example.com",
		"no-ipv4.example.com",
	}

	if len(result) != len(expected) {
		t.Fatalf("expected %d entries, got %d: %v", len(expected), len(result), result)
	}

	for i, exp := range expected {
		if result[i] != exp {
			t.Errorf("at index %d: expected %s, got %s", i, exp, result[i])
		}
	}
}

func TestPreResolveBypassEntries_EmptyAndNil(t *testing.T) {
	flushCalled := false
	mockFlush := func() {
		flushCalled = true
	}

	resNil := preResolveBypassEntriesWithResolver(nil, mockFlush, nil)
	if resNil != nil {
		t.Errorf("expected nil result for nil input, got: %v", resNil)
	}
	if !flushCalled {
		t.Error("expected flush to be called for nil input")
	}

	flushCalled = false
	resEmpty := preResolveBypassEntriesWithResolver([]string{}, mockFlush, nil)
	if resEmpty != nil {
		t.Errorf("expected nil result for empty input, got: %v", resEmpty)
	}
	if !flushCalled {
		t.Error("expected flush to be called for empty input")
	}
}

func TestPreResolveBypassEntries_PublicAPI(t *testing.T) {
	// Tests that the public PreResolveBypassEntries executes end-to-end
	// without panic on IP and CIDR entries (doesn't trigger external network resolution).
	input := []string{"192.168.0.0/16", "1.1.1.1", "1.1.1.1"}
	res := PreResolveBypassEntries(input)
	if len(res) != 2 || res[0] != "192.168.0.0/16" || res[1] != "1.1.1.1" {
		t.Fatalf("unexpected result from public PreResolveBypassEntries: %v", res)
	}
}

