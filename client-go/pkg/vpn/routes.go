package vpn

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"io"
	"log"
	"net"
	"os"
	"strings"
	"sync"
	"time"
)

// RouteEntry represents an installed routing table exception.
type RouteEntry struct {
	Destination    string `json:"destination"`
	Mask           string `json:"mask"`
	Gateway        string `json:"gateway"`
	Metric         int    `json:"metric"`
	InterfaceIndex int    `json:"interface_index,omitempty"`
}

// RouteManager manages bypass routing exceptions for VPN sessions.
type RouteManager struct {
	mu                   sync.Mutex
	cachedGateway        string
	cachedInterfaceIndex int
	cachedInterfaceIP    string
	activeRoutes         []RouteEntry

	// Pluggable functions for unit testing and mocking
	routeExecutor func(args ...string) error
	cmdRunner     func(name string, args ...string) (string, error)
	resolver      func(ctx context.Context, host string) ([]net.IP, error)
	ifaceFinder   func(targetIP string) int
}

// NewRouteManager creates a new RouteManager instance.
func NewRouteManager() *RouteManager {
	rm := &RouteManager{
		routeExecutor: defaultRouteExecutor,
		cmdRunner:     defaultCmdRunner,
		resolver: func(ctx context.Context, host string) ([]net.IP, error) {
			return net.DefaultResolver.LookupIP(ctx, "ip4", host)
		},
		ifaceFinder: defaultInterfaceFinder,
	}

	if gw, err := rm.DetectPhysicalGateway(); err == nil && gw != "" {
		rm.cachedGateway = gw
		if rm.cachedInterfaceIndex > 0 {
			log.Printf("[RouteManager] Discovered active physical default gateway: %s (IF index: %d)", gw, rm.cachedInterfaceIndex)
		} else {
			log.Printf("[RouteManager] Discovered active physical default gateway: %s", gw)
		}
	}

	return rm
}

func (rm *RouteManager) SetRouteExecutor(fn func(args ...string) error) {
	rm.mu.Lock()
	defer rm.mu.Unlock()
	rm.routeExecutor = fn
}

func (rm *RouteManager) SetCmdRunner(fn func(name string, args ...string) (string, error)) {
	rm.mu.Lock()
	defer rm.mu.Unlock()
	rm.cmdRunner = fn
}

func (rm *RouteManager) SetResolver(fn func(ctx context.Context, host string) ([]net.IP, error)) {
	rm.mu.Lock()
	defer rm.mu.Unlock()
	rm.resolver = fn
}

func (rm *RouteManager) SetInterfaceFinder(fn func(targetIP string) int) {
	rm.mu.Lock()
	defer rm.mu.Unlock()
	rm.ifaceFinder = fn
}

func (rm *RouteManager) SetCachedGateway(gw string) {
	rm.mu.Lock()
	defer rm.mu.Unlock()
	rm.cachedGateway = gw
}

func (rm *RouteManager) CachedGateway() string {
	rm.mu.Lock()
	defer rm.mu.Unlock()
	return rm.cachedGateway
}

func (rm *RouteManager) SetCachedInterfaceIndex(idx int) {
	rm.mu.Lock()
	defer rm.mu.Unlock()
	rm.cachedInterfaceIndex = idx
}

func (rm *RouteManager) CachedInterfaceIndex() int {
	rm.mu.Lock()
	defer rm.mu.Unlock()
	return rm.cachedInterfaceIndex
}

func (rm *RouteManager) DetectPhysicalGateway() (string, error) {
	rm.mu.Lock()
	defer rm.mu.Unlock()

	out, err := rm.cmdRunner("route", "print", "0.0.0.0")
	if err == nil {
		if gw, ifaceIP, parseErr := parseDefaultRouteFromRoutePrint(out); parseErr == nil && gw != "" {
			rm.cachedGateway = gw
			rm.cachedInterfaceIP = ifaceIP
			if rm.ifaceFinder != nil && ifaceIP != "" {
				if idx := rm.ifaceFinder(ifaceIP); idx > 0 {
					rm.cachedInterfaceIndex = idx
				}
			}
			return gw, nil
		}
	}

	netshOut, err := rm.cmdRunner("netsh", "interface", "ipv4", "show", "config")
	if err == nil {
		if gw, parseErr := parseDefaultGatewayFromNetsh(netshOut); parseErr == nil && gw != "" {
			rm.cachedGateway = gw
			return gw, nil
		}
	}

	if rm.cachedGateway != "" {
		return rm.cachedGateway, nil
	}

	return "", errors.New("unable to detect physical default gateway")
}

// ApplyBypassRoutes installs more-specific routes pointing to the physical gateway with metric 1.
// Supports CIDR subnets (e.g., "192.168.1.0/24"), single IPs ("1.2.3.4"), and domains ("gosuslugi.ru").
// Because of longest-prefix match, these routes take precedence over the default 0.0.0.0/0 VPN route.
// If the physical interface index is known, the route is explicitly bound to that interface via "if <ifIndex>".
func (rm *RouteManager) ApplyBypassRoutes(entries []string) (int, error) {
	rm.mu.Lock()
	defer rm.mu.Unlock()

	if len(entries) == 0 {
		return 0, nil
	}

	gw := rm.cachedGateway
	ifIdx := rm.cachedInterfaceIndex
	if gw == "" {
		out, err := rm.cmdRunner("route", "print", "0.0.0.0")
		if err == nil {
			if detected, ifaceIP, parseErr := parseDefaultRouteFromRoutePrint(out); parseErr == nil {
				gw = detected
				rm.cachedGateway = gw
				rm.cachedInterfaceIP = ifaceIP
				if rm.ifaceFinder != nil && ifaceIP != "" {
					if idx := rm.ifaceFinder(ifaceIP); idx > 0 {
						ifIdx = idx
						rm.cachedInterfaceIndex = idx
					}
				}
			}
		}
		if gw == "" {
			return 0, errors.New("cannot apply bypass routes: physical default gateway is unknown")
		}
	}

	type targetRoute struct {
		dest string
		mask string
	}

	seen := make(map[string]bool)
	var targets []targetRoute

	ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
	defer cancel()

	for _, raw := range entries {
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
				networkIP := ipNet.IP.To4()
				maskBytes := ipNet.Mask
				if len(maskBytes) == 4 {
					destStr := networkIP.String()
					maskStr := fmt.Sprintf("%d.%d.%d.%d", maskBytes[0], maskBytes[1], maskBytes[2], maskBytes[3])
					key := destStr + "/" + maskStr
					if !seen[key] {
						seen[key] = true
						targets = append(targets, targetRoute{dest: destStr, mask: maskStr})
					}
					continue
				}
			}
		}

		if ip := net.ParseIP(item); ip != nil {
			if v4 := ip.To4(); v4 != nil {
				destStr := v4.String()
				key := destStr + "/255.255.255.255"
				if !seen[key] {
					seen[key] = true
					targets = append(targets, targetRoute{dest: destStr, mask: "255.255.255.255"})
				}
				continue
			}
		}

		resolvedIPs, err := rm.resolver(ctx, item)
		if err != nil {
			log.Printf("[RouteManager] DNS resolution failed for %q: %v", item, err)
			continue
		}

		for _, ip := range resolvedIPs {
			if v4 := ip.To4(); v4 != nil {
				destStr := v4.String()
				key := destStr + "/255.255.255.255"
				if !seen[key] {
					seen[key] = true
					targets = append(targets, targetRoute{dest: destStr, mask: "255.255.255.255"})
				}
			}
		}
	}

	addedCount := 0
	for _, t := range targets {
		alreadyActive := false
		for _, ar := range rm.activeRoutes {
			if ar.Destination == t.dest && ar.Mask == t.mask && ar.Gateway == gw {
				alreadyActive = true
				break
			}
		}
		if alreadyActive {
			continue
		}

		var args []string
		if ifIdx > 0 {
			args = []string{"add", t.dest, "mask", t.mask, gw, "metric", "1", "if", fmt.Sprintf("%d", ifIdx)}
		} else {
			args = []string{"add", t.dest, "mask", t.mask, gw, "metric", "1"}
		}

		err := rm.routeExecutor(args...)
		if err != nil {
			log.Printf("[RouteManager] Failed to install bypass route for %s (mask %s, gw %s, if %d): %v", t.dest, t.mask, gw, ifIdx, err)
		} else {
			rm.activeRoutes = append(rm.activeRoutes, RouteEntry{
				Destination:    t.dest,
				Mask:           t.mask,
				Gateway:        gw,
				Metric:         1,
				InterfaceIndex: ifIdx,
			})
			addedCount++
		}
	}

	if ifIdx > 0 {
		log.Printf("[RouteManager] Installed %d bypass routes via physical gateway %s (IF %d)", addedCount, gw, ifIdx)
	} else {
		log.Printf("[RouteManager] Installed %d bypass routes via physical gateway %s", addedCount, gw)
	}
	return addedCount, nil
}

// ClearBypassRoutes cleanly deletes all previously tracked bypass routes.
func (rm *RouteManager) ClearBypassRoutes() int {
	rm.mu.Lock()
	defer rm.mu.Unlock()

	if len(rm.activeRoutes) == 0 {
		return 0
	}

	deletedCount := 0
	for _, entry := range rm.activeRoutes {
		err := rm.routeExecutor("delete", entry.Destination, "mask", entry.Mask)
		if err != nil {
			_ = rm.routeExecutor("delete", entry.Destination)
		}
		deletedCount++
	}

	log.Printf("[RouteManager] Cleanly removed %d bypass routes", deletedCount)
	rm.activeRoutes = nil
	return deletedCount
}

func (rm *RouteManager) GetActiveRoutes() []RouteEntry {
	rm.mu.Lock()
	defer rm.mu.Unlock()
	res := make([]RouteEntry, len(rm.activeRoutes))
	copy(res, rm.activeRoutes)
	return res
}

func ParseBypassExceptions(r io.Reader) ([]string, error) {
	var entries []string
	seen := make(map[string]bool)
	scanner := bufio.NewScanner(r)

	for scanner.Scan() {
		line := scanner.Text()

		for _, prefix := range []string{"#", "//", ";"} {
			if idx := strings.Index(line, prefix); idx >= 0 {
				line = line[:idx]
			}
		}

		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}

		tokens := strings.FieldsFunc(line, func(c rune) bool {
			return c == ',' || c == ' ' || c == '\t'
		})

		for _, token := range tokens {
			token = strings.TrimSpace(token)
			if token != "" && !seen[token] {
				seen[token] = true
				entries = append(entries, token)
			}
		}
	}

	if err := scanner.Err(); err != nil {
		return nil, fmt.Errorf("error reading bypass exceptions: %w", err)
	}

	return entries, nil
}

func ParseBypassExceptionsFile(filePath string) ([]string, error) {
	f, err := os.Open(filePath)
	if err != nil {
		return nil, fmt.Errorf("cannot open bypass exceptions file %s: %w", filePath, err)
	}
	defer f.Close()

	return ParseBypassExceptions(f)
}

func parseDefaultRouteFromRoutePrint(output string) (string, string, error) {
	type candidate struct {
		gw     string
		iface  string
		metric int
	}

	var candidates []candidate
	scanner := bufio.NewScanner(strings.NewReader(output))

	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		fields := strings.Fields(line)
		if len(fields) >= 5 && fields[0] == "0.0.0.0" && fields[1] == "0.0.0.0" {
			gwStr := fields[2]
			ifaceStr := fields[3]
			metricStr := fields[4]

			gwIP := net.ParseIP(gwStr)
			if gwIP == nil || gwIP.To4() == nil || gwIP.IsUnspecified() || gwIP.IsLoopback() {
				continue
			}

			ifaceIP := net.ParseIP(ifaceStr)
			if ifaceIP == nil || ifaceIP.To4() == nil {
				continue
			}

			var metric int
			fmt.Sscanf(metricStr, "%d", &metric)

			candidates = append(candidates, candidate{
				gw:     gwStr,
				iface:  ifaceStr,
				metric: metric,
			})
		}
	}

	if len(candidates) == 0 {
		return "", "", errors.New("no default gateway found in route print table")
	}

	if len(candidates) == 1 {
		return candidates[0].gw, candidates[0].iface, nil
	}

	best := candidates[0]
	for _, c := range candidates {
		if c.metric > best.metric {
			best = c
		}
	}

	return best.gw, best.iface, nil
}

func parseDefaultGatewayFromRoutePrint(output string) (string, error) {
	gw, _, err := parseDefaultRouteFromRoutePrint(output)
	return gw, err
}

func parseDefaultGatewayFromNetsh(output string) (string, error) {
	scanner := bufio.NewScanner(strings.NewReader(output))
	var currentInterface string

	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())

		if strings.HasPrefix(line, "Настройка интерфейса") || strings.HasPrefix(line, "Configuration for interface") {
			currentInterface = line
		}

		if strings.Contains(line, "Основной шлюз") || strings.Contains(line, "Default Gateway") {
			parts := strings.Split(line, ":")
			if len(parts) >= 2 {
				gw := strings.TrimSpace(parts[1])
				ip := net.ParseIP(gw)
				if ip != nil && ip.To4() != nil && !ip.IsUnspecified() && !ip.IsLoopback() {
					lowerIface := strings.ToLower(currentInterface)
					if !strings.Contains(lowerIface, "bobr") && !strings.Contains(lowerIface, "wintun") && !strings.Contains(lowerIface, "tap") {
						return gw, nil
					}
				}
			}
		}
	}

	return "", errors.New("no physical default gateway found in netsh config")
}
