package config

import (
	"time"
)

// Protocol constants for BobrDobr VPN.
const (
	ProtocolAmneziaWG   = "amneziawg"
	ProtocolOpenConnect = "openconnect"
)

// Status constants for VPN profiles.
const (
	StatusDisconnected = "disconnected"
	StatusConnecting   = "connecting"
	StatusConnected    = "connected"
	StatusError        = "error"
)

// Profile represents a VPN connection profile.
type Profile struct {
	ID             string              `json:"id"`
	Name           string              `json:"name"`
	Protocol       string              `json:"protocol"` // "amneziawg" or "openconnect"
	Server         string              `json:"server"`
	Port           int                 `json:"port"`
	Address        string              `json:"address,omitempty"`
	Status         string              `json:"status,omitempty"`
	CreatedAt      time.Time           `json:"created_at"`
	SplitTunnel    bool                `json:"split_tunnel"`
	BypassDomains  []string            `json:"bypass_domains,omitempty"`
	RawConfig      string              `json:"raw_config,omitempty"`
	AmneziaConfig  *AmneziaWGConfig    `json:"amnezia_config,omitempty"`
	OpenConnect    *OpenConnectConfig  `json:"openconnect_config,omitempty"`
	IsSubscription bool                `json:"is_subscription,omitempty"`
	SubID          string              `json:"sub_id,omitempty"`
}

// AmneziaWGConfig represents configuration parameters for AmneziaWG protocol.
type AmneziaWGConfig struct {
	ConfigContent string `json:"config_content,omitempty"`
	Address       string `json:"address"`
	DNS           string `json:"dns"`
	PrivateKey    string `json:"private_key"`
	PublicKey     string `json:"public_key"`
	PresharedKey  string `json:"preshared_key,omitempty"`
	Endpoint      string `json:"endpoint"`
	AllowedIPs    string `json:"allowed_ips"`
	Jc            int    `json:"jc"`
	Jmin          int    `json:"jmin"`
	Jmax          int    `json:"jmax"`
	S1            int    `json:"s1"`
	S2            int    `json:"s2"`
	H1            int    `json:"h1"`
	H2            int    `json:"h2"`
	H3            int    `json:"h3"`
	H4            int    `json:"h4"`
}

// OpenConnectConfig represents configuration parameters for OpenConnect protocol.
type OpenConnectConfig struct {
	Server      string `json:"server"`
	Port        int    `json:"port"`
	Username    string `json:"username"`
	Password    string `json:"password"`
	Protocol    string `json:"protocol"` // "anyconnect", "nc", "pulse", etc.
	Camouflage  string `json:"camouflage,omitempty"`
	ConnectURL  string `json:"connect_url,omitempty"`
	AuthGroup   string `json:"authgroup,omitempty"`
	ServerCert  string `json:"server_cert,omitempty"`
	CSCOToken   string `json:"csco_token,omitempty"`
	DisableIPv6 bool   `json:"disable_ipv6"`
}

// Settings represents persistent user preferences and application state.
type Settings struct {
	ActiveProfileID   string    `json:"active_profile_id"`
	AutoConnect       bool      `json:"auto_connect"`
	AutoStart         bool      `json:"auto_start"`
	CloseAction       string    `json:"close_action"` // "tray" (default) or "exit"
	SilentTray        bool      `json:"silent_tray"`
	Notifications     bool      `json:"notifications"`
	CheckUpdates      bool      `json:"check_updates"`
	KillSwitch        bool      `json:"kill_switch"`
	DNSLeakProtection bool      `json:"dns_leak_protection"`
	SubscriptionURL        string    `json:"subscription_url"`
	SubscriptionToken      string    `json:"subscription_token"`
	SubscriptionUsername   string    `json:"subscription_username,omitempty"`
	SubscriptionServer     string    `json:"subscription_server,omitempty"`
	SubscriptionExpiresAt  time.Time `json:"subscription_expires_at,omitempty"`
	SubscriptionStatus     string    `json:"subscription_status,omitempty"`
	LastSyncTime           time.Time `json:"last_sync_time"`
	Theme             string    `json:"theme"`
	Language          string    `json:"language"`
}

// DefaultSettings returns settings initialized with sane defaults.
func DefaultSettings() Settings {
	return Settings{
		AutoConnect:       false,
		AutoStart:         false,
		CloseAction:       "tray",
		SilentTray:        false,
		Notifications:     true,
		CheckUpdates:      true,
		KillSwitch:        false,
		DNSLeakProtection: true,
		Theme:             "dark",
		Language:          "ru",
	}
}
