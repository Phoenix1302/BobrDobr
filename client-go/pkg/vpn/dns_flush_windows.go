//go:build windows

package vpn

import (
	"log"
	"os/exec"

	"golang.org/x/sys/windows"
)

var (
	modDnsapi                 = windows.NewLazySystemDLL("dnsapi.dll")
	procDnsFlushResolverCache = modDnsapi.NewProc("DnsFlushResolverCache")
)

// FlushDNSCache flushes the Windows local DNS resolver cache.
// It calls DnsFlushResolverCache from dnsapi.dll and falls back to invoking
// "ipconfig /flushdns" with a hidden window.
func FlushDNSCache() {
	var flushed bool
	if err := procDnsFlushResolverCache.Find(); err == nil {
		r1, _, _ := procDnsFlushResolverCache.Call()
		if r1 != 0 {
			flushed = true
		}
	}

	if !flushed {
		cmd := exec.Command("ipconfig", "/flushdns")
		cmd.SysProcAttr = &windows.SysProcAttr{
			HideWindow:    true,
			CreationFlags: windows.CREATE_NO_WINDOW,
		}
		if err := cmd.Run(); err != nil {
			log.Printf("[FlushDNSCache] warning: ipconfig /flushdns failed: %v", err)
		} else {
			flushed = true
		}
	}

	if flushed {
		log.Printf("[FlushDNSCache] Local DNS resolver cache flushed")
	}
}
