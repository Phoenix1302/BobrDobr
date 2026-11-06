//go:build windows

package netadapter

import (
	"context"
	"errors"
	"os/exec"
	"strings"
	"sync"
	"syscall"
	"unsafe"

	"golang.org/x/sys/windows"
	"golang.org/x/sys/windows/registry"
)

var (
	modiphlpapi                    = windows.NewLazySystemDLL("iphlpapi.dll")
	procConvertInterfaceNameToLuid = modiphlpapi.NewProc("ConvertInterfaceNameToLuidW")
	procFlushIpPathTable           = modiphlpapi.NewProc("FlushIpPathTable")

	moddnsapi                 = windows.NewLazySystemDLL("dnsapi.dll")
	procDnsFlushResolverCache = moddnsapi.NewProc("DnsFlushResolverCache")

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

// GetAdapterStats queries real-time traffic statistics for a network adapter.
// Uses ConvertInterfaceNameToLuidW and windows.GetIfEntry2Ex.
func GetAdapterStats(name string) (AdapterStats, error) {
	nameTrimmed := strings.TrimSpace(name)
	if nameTrimmed == "" {
		return AdapterStats{}, errors.New("adapter name is empty")
	}

	mockStatsMu.RLock()
	if s, ok := mockStats[nameTrimmed]; ok {
		mockStatsMu.RUnlock()
		return s, nil
	}
	mockStatsMu.RUnlock()

	nameUTF16, err := windows.UTF16PtrFromString(nameTrimmed)
	if err != nil {
		return AdapterStats{}, err
	}

	if err := procConvertInterfaceNameToLuid.Find(); err != nil {
		return AdapterStats{}, err
	}

	var luid uint64
	r1, _, _ := procConvertInterfaceNameToLuid.Call(
		uintptr(unsafe.Pointer(nameUTF16)),
		uintptr(unsafe.Pointer(&luid)),
	)
	if r1 != 0 {
		return AdapterStats{}, windows.Errno(r1)
	}

	row := windows.MibIfRow2{InterfaceLuid: luid}
	if err := windows.GetIfEntry2Ex(0, &row); err != nil {
		return AdapterStats{}, err
	}

	return AdapterStats{
		RxBytes: row.InOctets,
		TxBytes: row.OutOctets,
	}, nil
}

// IsAdapterPresent checks if an interface exists in the Windows network stack.
// Uses ConvertInterfaceNameToLuidW for sub-millisecond execution with netsh fallback.
func IsAdapterPresent(name string) bool {
	if strings.TrimSpace(name) == "" {
		return false
	}

	if procConvertInterfaceNameToLuid.Find() == nil {
		nameUTF16, err := windows.UTF16PtrFromString(name)
		if err == nil {
			var luid uint64
			r1, _, _ := procConvertInterfaceNameToLuid.Call(
				uintptr(unsafe.Pointer(nameUTF16)),
				uintptr(unsafe.Pointer(&luid)),
			)
			if r1 == 0 {
				return true
			}
		}
	}

	// Fallback to netsh
	cmd := exec.Command("netsh", "interface", "show", "interface", "name="+name)
	cmd.SysProcAttr = &windows.SysProcAttr{HideWindow: true}
	out, err := cmd.Output()
	if err == nil && strings.Contains(strings.ToLower(string(out)), strings.ToLower(name)) {
		return true
	}

	return false
}

// IsAdapterBusy checks if an interface exists in the network stack or is registered
// in SWD\WINTUN registry during PnP teardown.
func IsAdapterBusy(name string) bool {
	target := strings.ToLower(strings.TrimSpace(name))
	if target == "" {
		return false
	}

	if IsAdapterPresent(target) {
		return true
	}

	// Check SWD\WINTUN registry nodes
	instances, err := GetWintunDeviceInstances()
	if err == nil {
		for _, inst := range instances {
			ifaceName, err := GetWintunInterfaceForInstance(inst)
			if err == nil && strings.ToLower(strings.TrimSpace(ifaceName)) == target {
				return true
			}
		}
	}

	return false
}

// GetWintunDeviceInstances returns a list of PnP device instance IDs for Wintun devices.
func GetWintunDeviceInstances() ([]string, error) {
	k, err := registry.OpenKey(
		registry.LOCAL_MACHINE,
		`SYSTEM\CurrentControlSet\Enum\SWD\WINTUN`,
		registry.READ,
	)
	if err != nil {
		return nil, err
	}
	defer k.Close()

	subkeys, err := k.ReadSubKeyNames(-1)
	if err != nil {
		return nil, err
	}

	var instances []string
	for _, sub := range subkeys {
		instances = append(instances, `SWD\WINTUN\`+sub)
	}
	return instances, nil
}

// GetWintunInterfaceForInstance maps an SWD\WINTUN\{GUID} instance to its network connection name.
func GetWintunInterfaceForInstance(instanceID string) (string, error) {
	parts := strings.Split(instanceID, `\`)
	guid := parts[len(parts)-1]

	// 1. Check Network Connection name in registry
	netPath := `SYSTEM\CurrentControlSet\Control\Network\{4d36e972-e325-11ce-bfc1-08002be10318}\` + guid + `\Connection`
	nk, err := registry.OpenKey(registry.LOCAL_MACHINE, netPath, registry.READ)
	if err == nil {
		defer nk.Close()
		name, _, err := nk.GetStringValue("Name")
		if err == nil && strings.TrimSpace(name) != "" {
			return strings.TrimSpace(name), nil
		}
	}

	// 2. Check FriendlyName or DeviceDesc under Enum\SWD\WINTUN\{guid}
	enumPath := `SYSTEM\CurrentControlSet\Enum\SWD\WINTUN\` + guid
	ek, err := registry.OpenKey(registry.LOCAL_MACHINE, enumPath, registry.READ)
	if err == nil {
		defer ek.Close()
		for _, prop := range []string{"FriendlyName", "DeviceDesc"} {
			val, _, err := ek.GetStringValue(prop)
			if err == nil {
				valTrim := strings.TrimSpace(val)
				valLower := strings.ToLower(valTrim)
				if valLower != "wireguard tunnel" && valLower != "wintun userspace tunnel" && valTrim != "" {
					return valTrim, nil
				}
			}
		}
	}

	return "", errors.New("interface name not found for instance")
}

// ScanOrphanAdapters discovers all Wintun / NetAdapter instances on Windows.
func ScanOrphanAdapters() ([]OrphanAdapter, error) {
	var results []OrphanAdapter
	seen := make(map[string]bool)

	// 1. Scan SWD\WINTUN registry
	instances, err := GetWintunDeviceInstances()
	if err == nil {
		for _, inst := range instances {
			ifaceName, _ := GetWintunInterfaceForInstance(inst)
			results = append(results, OrphanAdapter{
				InstanceID:    inst,
				InterfaceName: ifaceName,
				Description:   "Wintun Device",
			})
			if ifaceName != "" {
				seen[strings.ToLower(ifaceName)] = true
			}
		}
	}

	// 2. Scan Services\Wintun if present
	sk, err := registry.OpenKey(
		registry.LOCAL_MACHINE,
		`SYSTEM\CurrentControlSet\Services\Wintun`,
		registry.READ,
	)
	if err == nil {
		sk.Close()
	}

	// 3. Scan netsh interface list
	cmd := exec.Command("netsh", "interface", "show", "interface")
	cmd.SysProcAttr = &windows.SysProcAttr{HideWindow: true}
	out, err := cmd.Output()
	if err == nil {
		lines := strings.Split(string(out), "\n")
		for _, line := range lines {
			parts := strings.Fields(line)
			if len(parts) >= 4 {
				candName := parts[len(parts)-1]
				candLower := strings.ToLower(candName)
				if (strings.HasPrefix(candLower, "bobr") || strings.HasPrefix(candLower, "awg")) && !seen[candLower] {
					results = append(results, OrphanAdapter{
						InterfaceName: candName,
						Description:   "Netsh Interface",
					})
					seen[candLower] = true
				}
			}
		}
	}

	return results, nil
}

// CleanupOrphanAdapters scans and removes all lingering 'bobr*' and 'awg*' adapters
// that are not in the activeInterfaces whitelist.
// NEVER touches third-party adapters (Wi-Fi, Ethernet, Tailscale, ZeroTier, etc.).
func CleanupOrphanAdapters(ctx context.Context, activeInterfaces []string) error {
	orphans, err := ScanOrphanAdapters()
	if err != nil {
		return err
	}

	var wg sync.WaitGroup
	for _, o := range orphans {
		if ctx.Err() != nil {
			return ctx.Err()
		}

		if !IsSafeToClean(o.InterfaceName, activeInterfaces) {
			continue
		}

		instID := o.InstanceID
		ifaceName := o.InterfaceName

		wg.Add(1)
		go func(inst, iface string) {
			defer wg.Done()

			// Remove via pnputil if instance ID is known
			if inst != "" {
				cmd := exec.CommandContext(ctx, "pnputil.exe", "/remove-device", inst, "/subtree")
				cmd.SysProcAttr = &windows.SysProcAttr{HideWindow: true}
				_ = cmd.Run()
			}

			// Also try netsh or powershell if interface still present
			if iface != "" && IsAdapterPresent(iface) {
				psCmd := `Get-NetAdapter -Name '` + iface + `' -ErrorAction SilentlyContinue | ForEach-Object { if ($_.PnPDeviceID) { pnputil.exe /remove-device $_.PnPDeviceID /subtree | Out-Null } }`
				cmd := exec.CommandContext(ctx, "powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", psCmd)
				cmd.SysProcAttr = &windows.SysProcAttr{HideWindow: true}
				_ = cmd.Run()
			}
		}(instID, ifaceName)
	}

	wg.Wait()
	return nil
}

// DeleteAdapter removes a specific Wintun adapter by name.
func DeleteAdapter(ctx context.Context, interfaceName string) error {
	name := strings.TrimSpace(interfaceName)
	if name == "" {
		return nil
	}

	instances, err := GetWintunDeviceInstances()
	if err == nil {
		for _, inst := range instances {
			iface, _ := GetWintunInterfaceForInstance(inst)
			if strings.EqualFold(iface, name) {
				cmd := exec.CommandContext(ctx, "pnputil.exe", "/remove-device", inst, "/subtree")
				cmd.SysProcAttr = &windows.SysProcAttr{HideWindow: true}
				_ = cmd.Run()
			}
		}
	}

	if IsAdapterPresent(name) {
		psCmd := `Get-NetAdapter -Name '` + name + `' -ErrorAction SilentlyContinue | ForEach-Object { if ($_.PnPDeviceID) { pnputil.exe /remove-device $_.PnPDeviceID /subtree | Out-Null } }`
		cmd := exec.CommandContext(ctx, "powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", psCmd)
		cmd.SysProcAttr = &windows.SysProcAttr{HideWindow: true}
		return cmd.Run()
	}

	return nil
}

// FlushDNS flushes the Windows DNS resolver cache.
// Calls DnsFlushResolverCache from dnsapi.dll with ipconfig /flushdns fallback.
func FlushDNS(ctx context.Context) error {
	if procDnsFlushResolverCache.Find() == nil {
		r1, _, _ := procDnsFlushResolverCache.Call()
		if r1 != 0 {
			return nil
		}
	}

	cmd := exec.CommandContext(ctx, "ipconfig", "/flushdns")
	cmd.SysProcAttr = &windows.SysProcAttr{HideWindow: true}
	return cmd.Run()
}

// FlushRoutes flushes the IP routing cache table and removes default routes on interface.
// Uses FlushIpPathTable from iphlpapi.dll and netsh.
func FlushRoutes(ctx context.Context, interfaceName string) error {
	if procFlushIpPathTable.Find() == nil {
		// AF_INET = 2 (IPv4)
		_, _, _ = procFlushIpPathTable.Call(uintptr(syscall.AF_INET))
		// AF_INET6 = 23 (IPv6)
		_, _, _ = procFlushIpPathTable.Call(uintptr(23))
	}

	if strings.TrimSpace(interfaceName) != "" {
		// Reset routing table entries for the given interface
		cmd4 := exec.CommandContext(ctx, "netsh", "interface", "ipv4", "delete", "route", "0.0.0.0/0", "interface="+interfaceName)
		cmd4.SysProcAttr = &windows.SysProcAttr{HideWindow: true}
		_ = cmd4.Run()

		cmd6 := exec.CommandContext(ctx, "netsh", "interface", "ipv6", "delete", "route", "::/0", "interface="+interfaceName)
		cmd6.SysProcAttr = &windows.SysProcAttr{HideWindow: true}
		_ = cmd6.Run()
	}

	return nil
}
