package config

import (
	"encoding/base64"
	"errors"
	"fmt"
	"net"
	"strconv"
	"strings"
)

// Common validation errors.
var (
	ErrEmptyProfileID       = errors.New("profile ID cannot be empty")
	ErrEmptyProfileName     = errors.New("profile name cannot be empty")
	ErrInvalidProtocol     = errors.New("unsupported protocol: must be 'amneziawg' or 'openconnect'")
	ErrInvalidPort         = errors.New("port must be between 1 and 65535")
	ErrMissingAmneziaConfig = errors.New("amneziawg profile requires amnezia configuration")
	ErrMissingOpenConnect   = errors.New("openconnect profile requires openconnect configuration")
	ErrEmptyServerAddress   = errors.New("server address cannot be empty")
	ErrInvalidPrivateKey    = errors.New("invalid private key: must be valid base64 (32 bytes)")
	ErrInvalidPublicKey     = errors.New("invalid public key: must be valid base64 (32 bytes)")
	ErrInvalidEndpoint      = errors.New("invalid endpoint format: must be host:port or ip:port")
	ErrInvalidAddress       = errors.New("invalid address CIDR or IP")
	ErrInvalidAllowedIPs    = errors.New("invalid allowed IPs CIDR")
	ErrInvalidJunkParam     = errors.New("junk packet parameter must be non-negative")
	ErrJmaxLessThanJmin     = errors.New("Jmax cannot be less than Jmin")
	ErrInvalidHeaderParam   = errors.New("header magic number must be non-negative uint32")
)

// Validate checks the profile fields and its protocol-specific configuration.
func (p *Profile) Validate() error {
	if strings.TrimSpace(p.ID) == "" {
		return ErrEmptyProfileID
	}
	if strings.TrimSpace(p.Name) == "" {
		return ErrEmptyProfileName
	}

	proto := strings.ToLower(strings.TrimSpace(p.Protocol))
	if proto != ProtocolAmneziaWG && proto != ProtocolOpenConnect {
		return fmt.Errorf("%w: '%s'", ErrInvalidProtocol, p.Protocol)
	}

	if p.Port < 0 || p.Port > 65535 {
		return fmt.Errorf("%w: %d", ErrInvalidPort, p.Port)
	}

	switch proto {
	case ProtocolAmneziaWG:
		if p.AmneziaConfig == nil {
			return ErrMissingAmneziaConfig
		}
		if err := p.AmneziaConfig.Validate(); err != nil {
			return fmt.Errorf("amneziawg config validation failed: %w", err)
		}
	case ProtocolOpenConnect:
		if p.OpenConnect == nil {
			return ErrMissingOpenConnect
		}
		if err := p.OpenConnect.Validate(); err != nil {
			return fmt.Errorf("openconnect config validation failed: %w", err)
		}
	}

	return nil
}

// Validate checks the AmneziaWG configuration parameters.
func (c *AmneziaWGConfig) Validate() error {
	// Obfuscation junk checks
	if c.Jc < 0 {
		return fmt.Errorf("%w: Jc=%d", ErrInvalidJunkParam, c.Jc)
	}
	if c.Jmin < 0 {
		return fmt.Errorf("%w: Jmin=%d", ErrInvalidJunkParam, c.Jmin)
	}
	if c.Jmax < 0 {
		return fmt.Errorf("%w: Jmax=%d", ErrInvalidJunkParam, c.Jmax)
	}
	if c.Jc > 0 && c.Jmax < c.Jmin {
		return fmt.Errorf("%w: Jmax (%d) < Jmin (%d)", ErrJmaxLessThanJmin, c.Jmax, c.Jmin)
	}
	if c.S1 < 0 {
		return fmt.Errorf("%w: S1=%d", ErrInvalidJunkParam, c.S1)
	}
	if c.S2 < 0 {
		return fmt.Errorf("%w: S2=%d", ErrInvalidJunkParam, c.S2)
	}

	// Signature header magic numbers (must be non-negative uint32)
	const maxUint32 = 0xFFFFFFFF
	headers := []struct {
		name string
		val  int
	}{
		{"H1", c.H1},
		{"H2", c.H2},
		{"H3", c.H3},
		{"H4", c.H4},
	}
	for _, h := range headers {
		if h.val < 0 || h.val > maxUint32 {
			return fmt.Errorf("%w: %s=%d", ErrInvalidHeaderParam, h.name, h.val)
		}
	}

	// Validate WireGuard keys if provided
	if c.PrivateKey != "" {
		if err := validateWireguardKey(c.PrivateKey); err != nil {
			return fmt.Errorf("%w: %v", ErrInvalidPrivateKey, err)
		}
	}
	if c.PublicKey != "" {
		if err := validateWireguardKey(c.PublicKey); err != nil {
			return fmt.Errorf("%w: %v", ErrInvalidPublicKey, err)
		}
	}

	// Validate Endpoint if provided
	if c.Endpoint != "" {
		if err := validateEndpoint(c.Endpoint); err != nil {
			return fmt.Errorf("%w: %v", ErrInvalidEndpoint, err)
		}
	}

	// Validate Address (comma-separated CIDRs or IPs)
	if c.Address != "" {
		for _, addr := range strings.Split(c.Address, ",") {
			addr = strings.TrimSpace(addr)
			if addr == "" {
				continue
			}
			if _, _, err := net.ParseCIDR(addr); err != nil {
				if net.ParseIP(addr) == nil {
					return fmt.Errorf("%w: '%s'", ErrInvalidAddress, addr)
				}
			}
		}
	}

	// Validate AllowedIPs
	if c.AllowedIPs != "" {
		for _, item := range strings.Split(c.AllowedIPs, ",") {
			item = strings.TrimSpace(item)
			if item == "" {
				continue
			}
			if _, _, err := net.ParseCIDR(item); err != nil {
				if net.ParseIP(item) == nil {
					return fmt.Errorf("%w: '%s'", ErrInvalidAllowedIPs, item)
				}
			}
		}
	}

	return nil
}

// Validate checks the OpenConnect configuration parameters.
func (c *OpenConnectConfig) Validate() error {
	if strings.TrimSpace(c.Server) == "" {
		return ErrEmptyServerAddress
	}
	if c.Port < 1 || c.Port > 65535 {
		return fmt.Errorf("%w: %d", ErrInvalidPort, c.Port)
	}

	if c.Protocol != "" {
		proto := strings.ToLower(strings.TrimSpace(c.Protocol))
		validProtocols := map[string]bool{
			"anyconnect": true,
			"nc":         true,
			"pulse":      true,
			"f5":         true,
			"fortinet":   true,
			"gp":         true,
			"array":      true,
		}
		if !validProtocols[proto] {
			return fmt.Errorf("unrecognized openconnect protocol: %s", c.Protocol)
		}
	}

	return nil
}

// Validate checks Settings values.
func (s *Settings) Validate() error {
	if s.Theme != "" {
		theme := strings.ToLower(strings.TrimSpace(s.Theme))
		if theme != "dark" && theme != "light" && theme != "system" {
			return fmt.Errorf("invalid theme '%s': must be 'dark', 'light', or 'system'", s.Theme)
		}
	}
	if s.Language != "" {
		lang := strings.ToLower(strings.TrimSpace(s.Language))
		if lang != "ru" && lang != "en" {
			return fmt.Errorf("unsupported language '%s': must be 'ru' or 'en'", s.Language)
		}
	}
	return nil
}

// Helper: validateWireguardKey validates 32-byte base64 encoded WireGuard key.
func validateWireguardKey(key string) error {
	trimmed := strings.TrimSpace(key)
	decoded, err := base64.StdEncoding.DecodeString(trimmed)
	if err != nil {
		return err
	}
	if len(decoded) != 32 {
		return fmt.Errorf("key length must be 32 bytes, got %d", len(decoded))
	}
	return nil
}

// Helper: validateEndpoint checks if endpoint has valid host:port.
func validateEndpoint(ep string) error {
	trimmed := strings.TrimSpace(ep)
	host, portStr, err := net.SplitHostPort(trimmed)
	if err != nil {
		return err
	}
	if host == "" {
		return errors.New("empty host in endpoint")
	}
	port, err := strconv.Atoi(portStr)
	if err != nil || port < 1 || port > 65535 {
		return fmt.Errorf("invalid port in endpoint: %s", portStr)
	}
	return nil
}
