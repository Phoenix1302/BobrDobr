package vpn

import (
	"bytes"
	"context"
	"fmt"
	"net"
	"sort"
	"strings"
	"time"
)

// cidrsOverlap checks whether two IPv4 CIDR blocks have a non-empty intersection.
// Because CIDR blocks are aligned power-of-two subnets, two blocks overlap
// if and only if one completely contains the other.
func cidrsOverlap(a, b *net.IPNet) bool {
	aMask, _ := a.Mask.Size()
	bMask, _ := b.Mask.Size()
	if aMask <= bMask {
		return a.Contains(b.IP)
	}
	return b.Contains(a.IP)
}

// SubtractCIDRs recursively subtracts excludeCIDRs from baseCIDR and returns
// the remaining minimal set of non-overlapping CIDR blocks covering baseCIDR \ excludes.
func SubtractCIDRs(baseCIDR *net.IPNet, excludeCIDRs []*net.IPNet) []*net.IPNet {
	if baseCIDR == nil {
		return nil
	}

	baseV4 := baseCIDR.IP.To4()
	if baseV4 == nil {
		return []*net.IPNet{baseCIDR}
	}

	ones, bits := baseCIDR.Mask.Size()
	if bits != 32 || ones < 0 || ones > 32 {
		return []*net.IPNet{baseCIDR}
	}

	// Normalize base CIDR to its network address
	baseMask := net.CIDRMask(ones, 32)
	normBaseIP := make(net.IP, 4)
	copy(normBaseIP, baseV4)
	for i := 0; i < 4; i++ {
		normBaseIP[i] &= baseMask[i]
	}
	normBase := &net.IPNet{IP: normBaseIP, Mask: baseMask}

	if len(excludeCIDRs) == 0 {
		return []*net.IPNet{normBase}
	}

	// Filter and normalize excludes to only those overlapping with normBase
	var filteredExcludes []*net.IPNet
	for _, exc := range excludeCIDRs {
		if exc == nil {
			continue
		}
		excV4 := exc.IP.To4()
		if excV4 == nil {
			continue
		}
		eOnes, eBits := exc.Mask.Size()
		if eBits != 32 || eOnes < 0 || eOnes > 32 {
			continue
		}
		eMask := net.CIDRMask(eOnes, 32)
		normExcIP := make(net.IP, 4)
		copy(normExcIP, excV4)
		for i := 0; i < 4; i++ {
			normExcIP[i] &= eMask[i]
		}
		normExc := &net.IPNet{IP: normExcIP, Mask: eMask}

		if cidrsOverlap(normBase, normExc) {
			filteredExcludes = append(filteredExcludes, normExc)
		}
	}

	if len(filteredExcludes) == 0 {
		return []*net.IPNet{normBase}
	}

	// If any exclude completely covers normBase, normBase is entirely eliminated
	for _, exc := range filteredExcludes {
		eOnes, _ := exc.Mask.Size()
		if eOnes <= ones {
			return nil
		}
	}

	if ones >= 32 {
		return nil
	}

	// Split normBase into two equal halves (child prefix length = ones + 1)
	childOnes := ones + 1
	childMask := net.CIDRMask(childOnes, 32)

	leftIP := make(net.IP, 4)
	copy(leftIP, normBaseIP)
	leftNet := &net.IPNet{IP: leftIP, Mask: childMask}

	rightIP := make(net.IP, 4)
	copy(rightIP, normBaseIP)
	byteIdx := ones / 8
	bitIdx := 7 - (ones % 8)
	rightIP[byteIdx] |= (1 << bitIdx)
	rightNet := &net.IPNet{IP: rightIP, Mask: childMask}

	// Partition excludes into left and right subnets
	var leftExcludes, rightExcludes []*net.IPNet
	for _, exc := range filteredExcludes {
		if exc.IP[byteIdx]&(1<<bitIdx) == 0 {
			leftExcludes = append(leftExcludes, exc)
		} else {
			rightExcludes = append(rightExcludes, exc)
		}
	}

	var result []*net.IPNet
	if len(leftExcludes) == 0 {
		result = append(result, leftNet)
	} else {
		result = append(result, SubtractCIDRs(leftNet, leftExcludes)...)
	}

	if len(rightExcludes) == 0 {
		result = append(result, rightNet)
	} else {
		result = append(result, SubtractCIDRs(rightNet, rightExcludes)...)
	}

	return result
}

// CalculateAllowedIPsForBypass parses originalAllowedIPs, resolves bypass entries into
// IPv4 exclusions, subtracts them from the IPv4 base CIDR(s) (e.g. 0.0.0.0/0),
// and returns the compact comma-separated list of AllowedIPs, preserving any IPv6 entries (e.g. ::/0).
func CalculateAllowedIPsForBypass(
	originalAllowedIPs string,
	bypassEntries []string,
	resolver func(ctx context.Context, host string) ([]net.IP, error),
) (string, error) {
	if resolver == nil {
		resolver = func(ctx context.Context, host string) ([]net.IP, error) {
			return net.DefaultResolver.LookupIP(ctx, "ip4", host)
		}
	}

	// 1. Parse original AllowedIPs into IPv4 base CIDRs and preserved IPv6 entries
	var ipv4Bases []*net.IPNet
	var preservedIPv6 []string

	tokens := strings.Split(originalAllowedIPs, ",")
	for _, tok := range tokens {
		item := strings.TrimSpace(tok)
		if item == "" {
			continue
		}
		if ip, ipNet, err := net.ParseCIDR(item); err == nil {
			if ip.To4() != nil {
				ipv4Bases = append(ipv4Bases, ipNet)
			} else {
				preservedIPv6 = append(preservedIPv6, item)
			}
			continue
		}
		if ip := net.ParseIP(item); ip != nil {
			if v4 := ip.To4(); v4 != nil {
				ipv4Bases = append(ipv4Bases, &net.IPNet{IP: v4, Mask: net.CIDRMask(32, 32)})
			} else {
				preservedIPv6 = append(preservedIPv6, item)
			}
			continue
		}
		// Fallback: keep unparsed tokens
		preservedIPv6 = append(preservedIPv6, item)
	}

	if len(ipv4Bases) == 0 {
		_, defaultV4, _ := net.ParseCIDR("0.0.0.0/0")
		ipv4Bases = append(ipv4Bases, defaultV4)
	}

	// 2. Parse bypassEntries into excluded IPv4 CIDR blocks
	ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
	defer cancel()

	seenExcludes := make(map[string]bool)
	var excludeCIDRs []*net.IPNet

	addExclude := func(netCIDR *net.IPNet) {
		if netCIDR == nil {
			return
		}
		ones, _ := netCIDR.Mask.Size()
		v4 := netCIDR.IP.To4()
		if v4 == nil {
			return
		}
		key := fmt.Sprintf("%s/%d", v4.String(), ones)
		if !seenExcludes[key] {
			seenExcludes[key] = true
			excludeCIDRs = append(excludeCIDRs, netCIDR)
		}
	}

	for _, raw := range bypassEntries {
		item := strings.TrimSpace(raw)
		if item == "" || strings.HasPrefix(item, "#") || strings.HasPrefix(item, "//") || strings.HasPrefix(item, ";") {
			continue
		}

		if host, _, err := net.SplitHostPort(item); err == nil && !strings.Contains(item, "/") {
			item = host
		}

		if strings.Contains(item, "/") {
			ip, ipNet, err := net.ParseCIDR(item)
			if err == nil && ip.To4() != nil {
				addExclude(ipNet)
				continue
			}
		}

		if ip := net.ParseIP(item); ip != nil {
			if v4 := ip.To4(); v4 != nil {
				addExclude(&net.IPNet{IP: v4, Mask: net.CIDRMask(32, 32)})
				continue
			}
		}

		// Treat as domain name
		resolvedIPs, err := resolver(ctx, item)
		if err != nil {
			continue
		}
		for _, ip := range resolvedIPs {
			if v4 := ip.To4(); v4 != nil {
				addExclude(&net.IPNet{IP: v4, Mask: net.CIDRMask(32, 32)})
			}
		}
	}

	// If no valid excludes, return original string or normalized base
	if len(excludeCIDRs) == 0 {
		if strings.TrimSpace(originalAllowedIPs) != "" {
			return originalAllowedIPs, nil
		}
		var defaults []string
		for _, b := range ipv4Bases {
			defaults = append(defaults, b.String())
		}
		defaults = append(defaults, preservedIPv6...)
		return strings.Join(defaults, ", "), nil
	}

	// 3. Subtract excludes from each IPv4 base CIDR
	var remainingIPv4 []*net.IPNet
	for _, base := range ipv4Bases {
		sub := SubtractCIDRs(base, excludeCIDRs)
		remainingIPv4 = append(remainingIPv4, sub...)
	}

	// 4. Sort IPv4 subnets deterministically by IP and prefix length
	sort.Slice(remainingIPv4, func(i, j int) bool {
		cmp := bytes.Compare(remainingIPv4[i].IP.To4(), remainingIPv4[j].IP.To4())
		if cmp != 0 {
			return cmp < 0
		}
		onesI, _ := remainingIPv4[i].Mask.Size()
		onesJ, _ := remainingIPv4[j].Mask.Size()
		return onesI < onesJ
	})

	// 5. Construct final comma-separated list
	var resultList []string
	for _, netCIDR := range remainingIPv4 {
		resultList = append(resultList, netCIDR.String())
	}
	resultList = append(resultList, preservedIPv6...)

	return strings.Join(resultList, ", "), nil
}

// ExtractAllowedIPsFromConfig extracts the AllowedIPs value from the [Peer] section of an INI config.
func ExtractAllowedIPsFromConfig(confText string) string {
	lines := strings.Split(strings.ReplaceAll(confText, "\r\n", "\n"), "\n")
	inPeer := false
	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, "[") && strings.HasSuffix(trimmed, "]") {
			inPeer = strings.EqualFold(trimmed, "[Peer]")
			continue
		}
		if inPeer && strings.HasPrefix(strings.ToLower(trimmed), "allowedips") {
			parts := strings.SplitN(trimmed, "=", 2)
			if len(parts) == 2 {
				return strings.TrimSpace(parts[1])
			}
		}
	}
	return ""
}

// ReplaceAllowedIPsInConfig replaces or injects AllowedIPs in the [Peer] section of an INI config.
func ReplaceAllowedIPsInConfig(confText string, newAllowedIPs string) string {
	useCRLF := strings.Contains(confText, "\r\n")
	lineSep := "\n"
	if useCRLF {
		lineSep = "\r\n"
	}

	lines := strings.Split(strings.ReplaceAll(confText, "\r\n", "\n"), "\n")
	replaced := false
	inPeer := false
	peerFound := false
	var result []string

	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, "[") && strings.HasSuffix(trimmed, "]") {
			inPeer = strings.EqualFold(trimmed, "[Peer]")
			if inPeer {
				peerFound = true
			}
		}

		if inPeer && strings.HasPrefix(strings.ToLower(trimmed), "allowedips") {
			parts := strings.SplitN(trimmed, "=", 2)
			if len(parts) == 2 {
				result = append(result, "AllowedIPs = "+newAllowedIPs)
				replaced = true
				continue
			}
		}
		result = append(result, line)
	}

	if !replaced {
		if peerFound {
			var finalResult []string
			inserted := false
			for _, line := range result {
				finalResult = append(finalResult, line)
				trimmed := strings.TrimSpace(line)
				if !inserted && strings.EqualFold(trimmed, "[Peer]") {
					finalResult = append(finalResult, "AllowedIPs = "+newAllowedIPs)
					inserted = true
				}
			}
			return strings.Join(finalResult, lineSep)
		}

		// No [Peer] section found, append one
		result = append(result, "", "[Peer]", "AllowedIPs = "+newAllowedIPs)
		return strings.Join(result, lineSep)
	}

	return strings.Join(result, lineSep)
}

// PreResolveBypassEntries flushes the DNS cache and resolves domain names to IPv4 addresses
// before the VPN tunnel is activated. This ensures routing exceptions and AllowedIPs calculations
// are based on authentic destination IPs rather than DNS queries intercepted or spoofed by the VPN server.
func PreResolveBypassEntries(entries []string) []string {
	return preResolveBypassEntriesWithResolver(entries, FlushDNSCache, nil)
}

func preResolveBypassEntriesWithResolver(
	entries []string,
	flushFn func(),
	resolver func(ctx context.Context, network, host string) ([]net.IP, error),
) []string {
	if flushFn != nil {
		flushFn()
	}

	if len(entries) == 0 {
		return nil
	}

	if resolver == nil {
		resolver = net.DefaultResolver.LookupIP
	}

	seen := make(map[string]bool)
	var result []string

	for _, raw := range entries {
		item := strings.TrimSpace(raw)
		if item == "" || strings.HasPrefix(item, "#") || strings.HasPrefix(item, "//") || strings.HasPrefix(item, ";") {
			continue
		}

		if host, _, err := net.SplitHostPort(item); err == nil && !strings.Contains(item, "/") {
			item = host
		}

		// Check if entry is a CIDR subnet (e.g. 192.168.1.0/24)
		if strings.Contains(item, "/") {
			if ip, _, err := net.ParseCIDR(item); err == nil && ip.To4() != nil {
				if !seen[item] {
					seen[item] = true
					result = append(result, item)
				}
				continue
			}
		}

		// Check if entry is an IP address (e.g. 1.2.3.4)
		if ip := net.ParseIP(item); ip != nil {
			if v4 := ip.To4(); v4 != nil {
				ipStr := v4.String()
				if !seen[ipStr] {
					seen[ipStr] = true
					result = append(result, ipStr)
				}
				continue
			}
			// Non-IPv4 IP: keep directly if not seen
			if !seen[item] {
				seen[item] = true
				result = append(result, item)
			}
			continue
		}

		// Entry is a domain name: resolve it to IPv4 with a 3-second timeout
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		ips, err := resolver(ctx, "ip4", item)
		cancel()

		if err != nil || len(ips) == 0 {
			// If resolution fails (e.g. offline or unresolvable), keep original domain as fallback.
			if !seen[item] {
				seen[item] = true
				result = append(result, item)
			}
			continue
		}

		hasIPv4 := false
		for _, ip := range ips {
			if v4 := ip.To4(); v4 != nil {
				hasIPv4 = true
				ipStr := v4.String()
				if !seen[ipStr] {
					seen[ipStr] = true
					result = append(result, ipStr)
				}
			}
		}

		if !hasIPv4 {
			// No IPv4 addresses returned: keep original domain as fallback
			if !seen[item] {
				seen[item] = true
				result = append(result, item)
			}
		}
	}

	return result
}

