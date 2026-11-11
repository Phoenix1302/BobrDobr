package subscription

import (
	"bufio"
	"bytes"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/Phoenix1302/BobrDobr/pkg/config"
)

var (
	reSubSuffix = regexp.MustCompile(`(?i)(?:\s*-\s*sub)+$`)
	reUserInfoExpire = regexp.MustCompile(`expire=(\d+)`)
	ErrEmptyPayload   = errors.New("subscription payload is empty")
	ErrInvalidPayload = errors.New("unable to parse subscription payload")
)

const defaultCabinetURL = "https://example.com/cloud"

// FormatSubscriptionProfileName ensures the profile has a clean "-sub" suffix.
func FormatSubscriptionProfileName(name string) string {
	trimmed := strings.TrimSpace(name)
	if trimmed == "" {
		return "vpn-sub"
	}
	base := reSubSuffix.ReplaceAllString(trimmed, "")
	base = strings.TrimSpace(base)
	if base == "" {
		return "vpn-sub"
	}
	return base + "-sub"
}

// ParseAmneziaWGConfigText parses standard WireGuard / AmneziaWG configuration text.
func ParseAmneziaWGConfigText(content string) (*config.AmneziaWGConfig, string, int, error) {
	cfg := &config.AmneziaWGConfig{}
	var serverHost string
	var serverPort int

	scanner := bufio.NewScanner(strings.NewReader(content))
	var currentSection string

	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") || strings.HasPrefix(line, ";") {
			continue
		}

		if strings.HasPrefix(line, "[") && strings.HasSuffix(line, "]") {
			currentSection = strings.ToLower(strings.Trim(line, "[] \t"))
			continue
		}

		parts := strings.SplitN(line, "=", 2)
		if len(parts) != 2 {
			continue
		}
		key := strings.TrimSpace(parts[0])
		val := strings.TrimSpace(parts[1])
		keyLower := strings.ToLower(key)

		switch currentSection {
		case "interface":
			switch keyLower {
			case "address":
				cfg.Address = val
			case "dns":
				cfg.DNS = val
			case "privatekey":
				cfg.PrivateKey = val
			case "jc":
				cfg.Jc, _ = strconv.Atoi(val)
			case "jmin":
				cfg.Jmin, _ = strconv.Atoi(val)
			case "jmax":
				cfg.Jmax, _ = strconv.Atoi(val)
			case "s1":
				cfg.S1, _ = strconv.Atoi(val)
			case "s2":
				cfg.S2, _ = strconv.Atoi(val)
			case "h1":
				cfg.H1, _ = strconv.Atoi(val)
			case "h2":
				cfg.H2, _ = strconv.Atoi(val)
			case "h3":
				cfg.H3, _ = strconv.Atoi(val)
			case "h4":
				cfg.H4, _ = strconv.Atoi(val)
			}
		case "peer":
			switch keyLower {
			case "publickey":
				cfg.PublicKey = val
			case "presharedkey":
				cfg.PresharedKey = val
			case "allowedips":
				cfg.AllowedIPs = val
			case "endpoint":
				cfg.Endpoint = val
				host, portStr, err := net.SplitHostPort(val)
				if err == nil {
					serverHost = host
					serverPort, _ = strconv.Atoi(portStr)
				} else {
					serverHost = val
				}
			}
		}
	}

	if err := scanner.Err(); err != nil {
		return nil, "", 0, fmt.Errorf("failed to scan config text: %w", err)
	}

	return cfg, serverHost, serverPort, nil
}

// ExtractCabinetURL extracts or discovers the personal cabinet URL.
func ExtractCabinetURL(raw *rawSubscriptionResponse, subURL string) string {
	if raw != nil && strings.TrimSpace(raw.CabinetURL) != "" {
		return strings.TrimRight(strings.TrimSpace(raw.CabinetURL), "/")
	}

	// Try extracting origin domain from subscription URL and construct https://{host}/cloud
	if subURL != "" {
		target := strings.TrimSpace(subURL)
		if !strings.HasPrefix(target, "http://") && !strings.HasPrefix(target, "https://") {
			target = "https://" + target
		}
		if parsed, err := url.Parse(target); err == nil && parsed.Host != "" {
			return fmt.Sprintf("https://%s/cloud", parsed.Host)
		}
	}

	if raw != nil {
		if u := strings.TrimSpace(raw.DashboardURL); u != "" {
			return strings.TrimRight(u, "/")
		}
		if raw.Server != nil {
			if u := strings.TrimSpace(raw.Server.CabinetURL); u != "" {
				return strings.TrimRight(u, "/")
			}
			if u := strings.TrimSpace(raw.Server.DashboardURL); u != "" {
				return strings.TrimRight(u, "/")
			}
		}
	}

	return defaultCabinetURL
}

// ParseExpiresAt parses expiration date from response data or Subscription-Userinfo header.
func ParseExpiresAt(rawExpires any, userinfoHeader string) time.Time {
	// First check Subscription-Userinfo header
	if userinfoHeader != "" {
		if m := reUserInfoExpire.FindStringSubmatch(userinfoHeader); len(m) > 1 {
			if sec, err := strconv.ParseInt(m[1], 10, 64); err == nil && sec > 0 {
				return time.Unix(sec, 0).UTC()
			}
		}
	}

	if rawExpires == nil {
		return time.Time{}
	}

	switch v := rawExpires.(type) {
	case float64:
		if v > 0 {
			return time.Unix(int64(v), 0).UTC()
		}
	case int64:
		if v > 0 {
			return time.Unix(v, 0).UTC()
		}
	case int:
		if v > 0 {
			return time.Unix(int64(v), 0).UTC()
		}
	case string:
		str := strings.TrimSpace(v)
		if str == "" {
			return time.Time{}
		}

		// Try numeric unix timestamp in string
		if sec, err := strconv.ParseInt(str, 10, 64); err == nil && sec > 0 {
			return time.Unix(sec, 0).UTC()
		}

		layouts := []string{
			time.RFC3339Nano,
			time.RFC3339,
			"2006-01-02T15:04:05",
			"2006-01-02 15:04:05",
			"2006-01-02",
		}
		cleanStr := strings.Replace(str, "+00:00", "Z", 1)
		for _, layout := range layouts {
			if t, err := time.Parse(layout, cleanStr); err == nil {
				return t.UTC()
			}
		}
	}

	return time.Time{}
}

// CalculateState computes subscription statuses, days left, and expiration states.
func CalculateState(rawStatus string, expiresAt time.Time, now time.Time) (
	status SubscriptionStatus, daysLeft int, isActive, isFrozen, isExpired, isExpiringSoon bool) {

	cleanStatus := strings.ToLower(strings.TrimSpace(rawStatus))
	status = StatusActive

	if cleanStatus == "blocked" {
		status = StatusBlocked
		isFrozen = true
	} else if cleanStatus == "banned" {
		status = StatusBanned
		isFrozen = true
	} else if cleanStatus == "expired" {
		status = StatusExpired
		isExpired = true
		isFrozen = true
	} else if cleanStatus == "frozen" {
		status = StatusFrozen
		isFrozen = true
	}

	if !expiresAt.IsZero() {
		if now.After(expiresAt) {
			isExpired = true
			isFrozen = true
			if status != StatusBlocked && status != StatusBanned {
				status = StatusExpired
			}
			daysLeft = 0
		} else {
			diff := expiresAt.Sub(now)
			daysLeft = int(diff.Hours() / 24)
			if daysLeft >= 0 && daysLeft <= 3 {
				isExpiringSoon = true
				if status == StatusActive {
					status = StatusExpiring
				}
			}
		}
	}

	isActive = !isFrozen && !isExpired && (status == StatusActive || status == StatusExpiring)
	return
}

// DecodeSubscriptionPayload parses raw bytes (JSON or base64) into SubscriptionInfo with profiles.
func DecodeSubscriptionPayload(raw []byte, subURL string, userinfoHeader string) (*SubscriptionInfo, error) {
	trimmed := bytes.TrimSpace(raw)
	if len(trimmed) == 0 {
		return nil, ErrEmptyPayload
	}

	// Try base64 decode if payload doesn't start with JSON '{' or '['
	workingPayload := trimmed
	if !bytes.HasPrefix(trimmed, []byte("{")) && !bytes.HasPrefix(trimmed, []byte("[")) {
		// Clean linebreaks / whitespaces from base64
		cleanedB64 := strings.ReplaceAll(string(trimmed), "\r", "")
		cleanedB64 = strings.ReplaceAll(cleanedB64, "\n", "")
		cleanedB64 = strings.ReplaceAll(cleanedB64, " ", "")

		if decoded, err := base64.StdEncoding.DecodeString(cleanedB64); err == nil && len(decoded) > 0 {
			workingPayload = bytes.TrimSpace(decoded)
		} else if decodedURL, err := base64.URLEncoding.DecodeString(cleanedB64); err == nil && len(decodedURL) > 0 {
			workingPayload = bytes.TrimSpace(decodedURL)
		} else if decodedRaw, err := base64.RawStdEncoding.DecodeString(cleanedB64); err == nil && len(decodedRaw) > 0 {
			workingPayload = bytes.TrimSpace(decodedRaw)
		}
	}

	// Case 1: Standard JSON object
	var resp rawSubscriptionResponse
	if err := json.Unmarshal(workingPayload, &resp); err == nil && (resp.Connections != nil || resp.Profiles != nil || resp.Servers != nil || resp.User != nil || resp.Status != "") {
		return parseFromRawResponse(&resp, workingPayload, subURL, userinfoHeader)
	}

	// Case 2: Direct JSON array of connections `[...]`
	var connections []rawConnection
	if err := json.Unmarshal(workingPayload, &connections); err == nil && len(connections) > 0 {
		resp = rawSubscriptionResponse{
			Connections: connections,
			Status:      "active",
		}
		return parseFromRawResponse(&resp, workingPayload, subURL, userinfoHeader)
	}

	// Case 3: Raw WireGuard / AmneziaWG .conf text
	if bytes.Contains(workingPayload, []byte("[Interface]")) {
		confText := string(workingPayload)
		awgCfg, srvHost, srvPort, err := ParseAmneziaWGConfigText(confText)
		if err == nil {
			prof := config.Profile{
				ID:             "sub-awg-raw",
				Name:           "vpn-sub",
				Protocol:       config.ProtocolAmneziaWG,
				Server:         srvHost,
				Port:           srvPort,
				CreatedAt:      time.Now().UTC(),
				AmneziaConfig:  awgCfg,
				IsSubscription: true,
				SubID:          "raw-conf",
			}
			now := time.Now().UTC()
			return &SubscriptionInfo{
				URL:         subURL,
				CabinetURL:  ExtractCabinetURL(nil, subURL),
				Status:      StatusActive,
				IsActive:    true,
				Profiles:    []config.Profile{prof},
				ServerHost:  srvHost,
				LastSync:    now,
				RawResponse: workingPayload,
			}, nil
		}
	}

	return nil, fmt.Errorf("%w: unrecognized format", ErrInvalidPayload)
}

func parseFromRawResponse(resp *rawSubscriptionResponse, raw []byte, subURL, userinfoHeader string) (*SubscriptionInfo, error) {
	// Consolidate connections
	allConns := resp.Connections
	if len(allConns) == 0 {
		allConns = resp.Profiles
	}
	if len(allConns) == 0 {
		allConns = resp.Servers
	}

	info := &SubscriptionInfo{
		URL:         subURL,
		CabinetURL:  ExtractCabinetURL(resp, subURL),
		LastSync:    time.Now().UTC(),
		RawResponse: raw,
	}

	// User details
	var rawExpires any
	if resp.User != nil {
		if resp.User.ID != nil {
			info.UserID = fmt.Sprintf("%v", resp.User.ID)
		}
		info.Username = resp.User.Username
		info.Role = resp.User.Role
		rawExpires = resp.User.ExpiresAt
	}

	// Server info
	if resp.Server != nil {
		info.ServerHost = resp.Server.Host
		info.AppVersion = resp.Server.AppVersion
	}

	// Expiry calculation
	info.ExpiresAt = ParseExpiresAt(rawExpires, userinfoHeader)
	status, daysLeft, isActive, isFrozen, isExpired, isExpiringSoon := CalculateState(resp.Status, info.ExpiresAt, info.LastSync)
	info.Status = status
	info.DaysLeft = daysLeft
	info.IsActive = isActive
	info.IsFrozen = isFrozen
	info.IsExpired = isExpired
	info.IsExpiringSoon = isExpiringSoon

	// Check is_frozen from response body or user
	frozenVal := parseFrozenValue(resp.IsFrozen)
	if frozenVal == 0 && resp.User != nil {
		frozenVal = parseFrozenValue(resp.User.IsFrozen)
	}

	if frozenVal == 2 {
		info.Status = StatusBlocked
		info.IsFrozen = true
		info.IsActive = false
	} else if frozenVal == 1 {
		info.Status = StatusExpired
		info.IsExpired = true
		info.IsFrozen = true
		info.IsActive = false
	}

	// Convert connections to Profiles
	profiles := make([]config.Profile, 0, len(allConns))
	for i, conn := range allConns {
		prof := convertConnectionToProfile(&conn, i+1)
		if prof != nil {
			profiles = append(profiles, *prof)
		}
	}
	info.Profiles = profiles

	return info, nil
}

func convertConnectionToProfile(conn *rawConnection, index int) *config.Profile {
	proto := strings.ToLower(strings.TrimSpace(conn.Proto))
	rawName := strings.TrimSpace(conn.Name)
	if rawName == "" {
		rawName = fmt.Sprintf("Profile %d", index)
	}
	profName := FormatSubscriptionProfileName(rawName)

	connID := ""
	if conn.ID != nil {
		connID = fmt.Sprintf("%v", conn.ID)
	} else {
		connID = fmt.Sprintf("sub-%d", index)
	}

	switch proto {
	case "awg", "amnezia", "amneziawg":
		awgCfg := &config.AmneziaWGConfig{
			Address:      conn.Address,
			DNS:          conn.DNS,
			PrivateKey:   conn.PrivateKey,
			PublicKey:    conn.PublicKey,
			PresharedKey: conn.PresharedKey,
			Endpoint:     conn.Endpoint,
			AllowedIPs:   conn.AllowedIPs,
			Jc:           conn.Jc,
			Jmin:         conn.Jmin,
			Jmax:         conn.Jmax,
			S1:           conn.S1,
			S2:           conn.S2,
			H1:           conn.H1,
			H2:           conn.H2,
			H3:           conn.H3,
			H4:           conn.H4,
		}
		if conn.IP != "" && awgCfg.Address == "" {
			awgCfg.Address = conn.IP
		}

		serverHost := conn.Host
		if serverHost == "" {
			serverHost = conn.Server
		}
		var serverPort int

		// Parse embedded conf content if available
		confText := conn.ConfigContent
		if confText == "" {
			confText = conn.ConfigText
		}
		if confText != "" {
			awgCfg.ConfigContent = confText
			if parsedCfg, sHost, sPort, err := ParseAmneziaWGConfigText(confText); err == nil {
				// Overlay parsed parameters if not already populated
				if awgCfg.Address == "" {
					awgCfg.Address = parsedCfg.Address
				}
				if awgCfg.DNS == "" {
					awgCfg.DNS = parsedCfg.DNS
				}
				if awgCfg.PrivateKey == "" {
					awgCfg.PrivateKey = parsedCfg.PrivateKey
				}
				if awgCfg.PublicKey == "" {
					awgCfg.PublicKey = parsedCfg.PublicKey
				}
				if awgCfg.PresharedKey == "" {
					awgCfg.PresharedKey = parsedCfg.PresharedKey
				}
				if awgCfg.Endpoint == "" {
					awgCfg.Endpoint = parsedCfg.Endpoint
				}
				if awgCfg.AllowedIPs == "" {
					awgCfg.AllowedIPs = parsedCfg.AllowedIPs
				}
				if awgCfg.Jc == 0 && parsedCfg.Jc != 0 {
					awgCfg.Jc = parsedCfg.Jc
				}
				if awgCfg.Jmin == 0 && parsedCfg.Jmin != 0 {
					awgCfg.Jmin = parsedCfg.Jmin
				}
				if awgCfg.Jmax == 0 && parsedCfg.Jmax != 0 {
					awgCfg.Jmax = parsedCfg.Jmax
				}
				if awgCfg.S1 == 0 && parsedCfg.S1 != 0 {
					awgCfg.S1 = parsedCfg.S1
				}
				if awgCfg.S2 == 0 && parsedCfg.S2 != 0 {
					awgCfg.S2 = parsedCfg.S2
				}
				if awgCfg.H1 == 0 && parsedCfg.H1 != 0 {
					awgCfg.H1 = parsedCfg.H1
				}
				if awgCfg.H2 == 0 && parsedCfg.H2 != 0 {
					awgCfg.H2 = parsedCfg.H2
				}
				if awgCfg.H3 == 0 && parsedCfg.H3 != 0 {
					awgCfg.H3 = parsedCfg.H3
				}
				if awgCfg.H4 == 0 && parsedCfg.H4 != 0 {
					awgCfg.H4 = parsedCfg.H4
				}
				if serverHost == "" {
					serverHost = sHost
				}
				if serverPort == 0 {
					serverPort = sPort
				}
			}
		}

		if serverHost == "" && awgCfg.Endpoint != "" {
			h, p, err := net.SplitHostPort(awgCfg.Endpoint)
			if err == nil {
				serverHost = h
				serverPort, _ = strconv.Atoi(p)
			}
		}

		return &config.Profile{
			ID:             connID,
			Name:           profName,
			Protocol:       config.ProtocolAmneziaWG,
			Server:         serverHost,
			Port:           serverPort,
			Address:        awgCfg.Address,
			RawConfig:      confText,
			CreatedAt:      time.Now().UTC(),
			AmneziaConfig:  awgCfg,
			IsSubscription: true,
			SubID:          connID,
		}

	case "ocserv", "openconnect":
		serverHost := conn.Server
		if serverHost == "" {
			serverHost = conn.Host
		}

		port := 443
		if conn.Port != nil {
			switch p := conn.Port.(type) {
			case float64:
				port = int(p)
			case int:
				port = p
			case string:
				if pi, err := strconv.Atoi(p); err == nil {
					port = pi
				}
			}
		}

		proto := conn.Protocol
		if proto == "" {
			proto = "anyconnect"
		}

		// Camouflage handling
		camoSecret := ""
		if conn.Camouflage != nil && conn.Camouflage.Enabled {
			camoSecret = strings.TrimLeft(conn.Camouflage.Secret, "/?")
			if camoSecret != "" && !strings.Contains(serverHost, "?") {
				serverHost = fmt.Sprintf("%s/?%s", serverHost, camoSecret)
			}
		}

		ocCfg := &config.OpenConnectConfig{
			Server:      serverHost,
			Port:        port,
			Username:    conn.Username,
			Password:    conn.Password,
			Protocol:    proto,
			Camouflage:  camoSecret,
			DisableIPv6: false,
		}

		return &config.Profile{
			ID:             connID,
			Name:           profName,
			Protocol:       config.ProtocolOpenConnect,
			Server:         serverHost,
			Port:           port,
			CreatedAt:      time.Now().UTC(),
			OpenConnect:    ocCfg,
			IsSubscription: true,
			SubID:          connID,
		}

	default:
		return nil
	}
}
