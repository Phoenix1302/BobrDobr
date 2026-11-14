package main

import (
	"bufio"
	"flag"
	"fmt"
	"io"
	"net/url"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"

	"openconnect-worker/auth"
	"openconnect-worker/base"
	"openconnect-worker/session"
	"openconnect-worker/utils/vpnc"
	"openconnect-worker/vpn"
)

func main() {
	// Parse CLI flags
	var (
		serverFlag        string
		userFlag          string
		passFlag          string
		groupFlag         string
		secretFlag        string
		ifaceFlag         string
		insecureFlag      bool
		noCertCheckFlag   bool
		noDtlsFlag        bool
		passwdOnStdinFlag bool
		nonInterFlag      bool
		verboseFlag       bool
		stdinControlFlag  bool
		logLevelFlag      string
		logPathFlag       string
	)

	flag.StringVar(&serverFlag, "server", "", "VPN server host or URL (e.g. vpn.example.com, https://vpn.example.com:443/?secret=example)")
	flag.StringVar(&serverFlag, "s", "", "VPN server (shorthand)")

	flag.StringVar(&userFlag, "username", "", "VPN user name")
	flag.StringVar(&userFlag, "user", "", "VPN user name (alias)")
	flag.StringVar(&userFlag, "u", "", "VPN user name (shorthand)")

	flag.StringVar(&passFlag, "password", "", "VPN password")
	flag.StringVar(&passFlag, "p", "", "VPN password (shorthand)")

	flag.BoolVar(&passwdOnStdinFlag, "passwd-on-stdin", false, "Read password strictly from standard input")

	flag.StringVar(&groupFlag, "authgroup", "", "VPN user group")
	flag.StringVar(&groupFlag, "group", "", "VPN user group (alias)")
	flag.StringVar(&groupFlag, "g", "", "VPN user group (shorthand)")

	flag.StringVar(&secretFlag, "secret", "", "Camouflage secret token (e.g. secret)")
	flag.StringVar(&secretFlag, "key", "", "Camouflage secret token (alias)")
	flag.StringVar(&secretFlag, "k", "", "Camouflage secret token (shorthand)")

	flag.StringVar(&ifaceFlag, "interface", "bobr-oc0", "Wintun tunnel interface name")
	flag.StringVar(&ifaceFlag, "i", "bobr-oc0", "Wintun tunnel interface name (shorthand)")

	flag.BoolVar(&insecureFlag, "insecure", true, "Allow untrusted / self-signed TLS certificates")
	flag.BoolVar(&noCertCheckFlag, "no-cert-check", true, "Do not check server certificate (compatibility)")

	flag.BoolVar(&noDtlsFlag, "no-dtls", false, "Disable DTLS and force TLS (CSTP) channel")
	flag.BoolVar(&nonInterFlag, "non-inter", false, "Non-interactive mode (compatibility)")
	flag.BoolVar(&stdinControlFlag, "stdin-control", false, "Close tunnel gracefully when standard input pipe is closed (EOF)")
	flag.BoolVar(&verboseFlag, "verbose", true, "Enable verbose logging")
	flag.BoolVar(&verboseFlag, "v", true, "Enable verbose logging (shorthand)")

	flag.StringVar(&logLevelFlag, "log_level", "info", "Log level (debug, info, warn, error)")
	flag.StringVar(&logPathFlag, "log_path", "", "Log directory path (empty = stdout)")

	flag.Parse()

	// If server not set via flag, check positional arguments
	targetServer := strings.TrimSpace(serverFlag)
	if targetServer == "" && flag.NArg() > 0 {
		targetServer = strings.TrimSpace(flag.Arg(0))
	}

	if targetServer == "" {
		fmt.Fprintf(os.Stderr, "Usage: openconnect-worker.exe [flags] <server>\n")
		fmt.Fprintf(os.Stderr, "Example: openconnect-worker.exe --passwd-on-stdin --user user -k secret vpn.example.com:443\n")
		flag.PrintDefaults()
		os.Exit(1)
	}

	// Initialize Logging
	base.Cfg.LogLevel = logLevelFlag
	if verboseFlag {
		base.Cfg.LogLevel = "debug"
	}
	base.Cfg.LogPath = logPathFlag
	base.Cfg.InsecureSkipVerify = insecureFlag || noCertCheckFlag
	base.Cfg.NoDTLS = noDtlsFlag
	base.Cfg.InterfaceName = ifaceFlag
	base.Cfg.CiscoCompat = true
	base.Cfg.AgentVersion = "4.10.07062"
	base.InitLog()

	base.Info("[openconnect-worker] OpenConnect Pure-Go CSTP Worker starting...")

	// Normalize server URL and parse camouflage secret if embedded
	parsedHost, parsedPort, parsedSecret := parseTarget(targetServer)
	if secretFlag == "" && parsedSecret != "" {
		secretFlag = parsedSecret
	}

	auth.Prof.Host = parsedHost
	if parsedPort != 0 && parsedPort != 443 {
		auth.Prof.HostWithPort = fmt.Sprintf("%s:%d", parsedHost, parsedPort)
	} else if strings.Contains(parsedHost, ":") {
		auth.Prof.HostWithPort = parsedHost
	} else {
		auth.Prof.HostWithPort = fmt.Sprintf("%s:443", parsedHost)
	}

	auth.Prof.Username = userFlag
	auth.Prof.Group = groupFlag
	auth.Prof.SecretKey = strings.TrimLeft(secretFlag, "/?")

	// Handle Password input
	password := passFlag
	stdinReader := bufio.NewReader(os.Stdin)

	if passwdOnStdinFlag || password == "" {
		// Read password from first line of stdin
		line, err := stdinReader.ReadString('\n')
		if err != nil && err != io.EOF {
			base.Fatal("Failed to read password from stdin:", err)
		}
		password = strings.TrimRight(line, "\r\n")
	}
	auth.Prof.Password = password

	// Channel for graceful termination
	stopCh := make(chan struct{})
	triggerStop := func(reason string) {
		select {
		case <-stopCh:
		default:
			base.Info("[openconnect-worker] Stop triggered:", reason)
			close(stopCh)
		}
	}

	// 1. Monitor os.Stdin in background: when closed (EOF) by parent supervisor or receives STOP -> exit
	go func() {
		for {
			line, err := stdinReader.ReadString('\n')
			if err != nil {
				if err == io.EOF {
					if stdinControlFlag {
						triggerStop("Standard input pipe closed (EOF)")
					}
					return
				}
				if stdinControlFlag {
					triggerStop(fmt.Sprintf("Stdin read error: %v", err))
				}
				return
			}
			cmd := strings.ToUpper(strings.TrimSpace(line))
			if cmd == "STOP" || cmd == "QUIT" || cmd == "EXIT" {
				triggerStop(fmt.Sprintf("Received command: %s", cmd))
				return
			}
		}
	}()

	// 2. Monitor OS signals (Ctrl+C, SIGTERM)
	sigCh := make(chan os.Signal, 2)
	signal.Notify(sigCh, os.Interrupt, syscall.SIGTERM)
	go func() {
		sig := <-sigCh
		triggerStop(fmt.Sprintf("Received OS signal: %v", sig))
	}()

	// Resolve local network interface and default physical gateway
	base.Info("Detecting local physical network interface...")
	if err := vpnc.GetLocalInterface(); err != nil {
		base.Fatal("Failed to detect local physical interface:", err)
	}

	// Step 1: AnyConnect XML Authentication Handshake
	base.Info("Initiating authentication with server:", auth.Prof.HostWithPort)
	if err := auth.InitAuth(); err != nil {
		base.Fatal("InitAuth failed:", err)
	}

	if err := auth.PasswordAuth(); err != nil {
		base.Fatal(err)
	}
	base.Info("Authentication successful, session token acquired")

	// Step 2: Establish CSTP Tunnel & Wintun Virtual Adapter
	base.Info("Establishing AnyConnect CSTP tunnel...")
	if err := vpn.SetupTunnel(); err != nil {
		base.Fatal("SetupTunnel failed:", err)
	}

	base.Info("[openconnect-worker] CSTP tunnel established and ready.")

	// Main wait loop: wait until termination signal or connection drops
	select {
	case <-stopCh:
		base.Info("User cancelled; initiating graceful termination...")
	case <-session.Sess.CloseChan:
		base.Info("Session terminated by server or network layer.")
	}

	// Step 3: Graceful Teardown & AnyConnect CSTP BYE Packet
	shutdownTimeout := 2500 * time.Millisecond
	doneCh := make(chan struct{})

	go func() {
		session.Sess.ActiveClose = true
		if session.Sess.CSess != nil {
			vpnc.ResetRoutes(session.Sess.CSess)
			session.Sess.CSess.SendBye(auth.Conn)
			session.Sess.CSess.Close()
		}
		close(doneCh)
	}()

	select {
	case <-doneCh:
		base.Info("[openconnect-worker] Logout of session completed (clean shutdown)")
	case <-time.After(shutdownTimeout):
		base.Warn("[openconnect-worker] Shutdown timeout elapsed; forcing exit")
	}

	base.Info("[openconnect-worker] Tunnel interface closed, session terminated cleanly.")
	os.Exit(0)
}

// parseTarget parses a server string which can be a hostname, host:port, or full URL with query
func parseTarget(target string) (host string, port int, secret string) {
	raw := strings.TrimSpace(target)
	if strings.Contains(raw, "://") {
		u, err := url.Parse(raw)
		if err == nil {
			host = u.Hostname()
			if p := u.Port(); p != "" {
				port, _ = strconv.Atoi(p)
			}
			secret = u.RawQuery
			if secret == "" && u.Path != "" && u.Path != "/" {
				secret = strings.Trim(u.Path, "/")
			}
			return
		}
	}

	// Format: host/?secret or host:port/?secret
	if strings.Contains(raw, "?") {
		parts := strings.SplitN(raw, "?", 2)
		raw = parts[0]
		secret = parts[1]
	}

	raw = strings.TrimRight(raw, "/")
	if strings.Contains(raw, "/") {
		parts := strings.SplitN(raw, "/", 2)
		raw = parts[0]
		if secret == "" {
			secret = parts[1]
		}
	}

	if strings.Contains(raw, ":") {
		parts := strings.SplitN(raw, ":", 2)
		host = parts[0]
		port, _ = strconv.Atoi(parts[1])
	} else {
		host = raw
		port = 443
	}

	// Special check if secret contains port (e.g. kurwa:443)
	if strings.Contains(secret, ":") {
		secParts := strings.SplitN(secret, ":", 2)
		secret = secParts[0]
		if port == 443 {
			if p, err := strconv.Atoi(secParts[1]); err == nil && p > 0 {
				port = p
			}
		}
	}

	return
}
