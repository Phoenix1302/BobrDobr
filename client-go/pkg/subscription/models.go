package subscription

import (
	"time"

	"github.com/Phoenix1302/BobrDobr/pkg/config"
)

// SubscriptionStatus indicates the operational status of a subscription.
type SubscriptionStatus string

const (
	StatusActive   SubscriptionStatus = "active"
	StatusExpiring SubscriptionStatus = "expiring"
	StatusExpired  SubscriptionStatus = "expired"
	StatusBlocked  SubscriptionStatus = "blocked"
	StatusBanned   SubscriptionStatus = "banned"
	StatusFrozen   SubscriptionStatus = "frozen"
	StatusUnknown  SubscriptionStatus = "unknown"
)

// SubscriptionInfo holds the parsed and processed details of a subscription bundle.
type SubscriptionInfo struct {
	URL            string             `json:"url"`
	CabinetURL     string             `json:"cabinet_url"`
	UserID         string             `json:"user_id"`
	Username       string             `json:"username"`
	Role           string             `json:"role"`
	Status         SubscriptionStatus `json:"status"`
	ExpiresAt      time.Time          `json:"expires_at"`
	DaysLeft       int                `json:"days_left"`
	IsActive       bool               `json:"is_active"`
	IsFrozen       bool               `json:"is_frozen"`
	IsExpired      bool               `json:"is_expired"`
	IsExpiringSoon bool               `json:"is_expiring_soon"`
	Profiles       []config.Profile   `json:"profiles"`
	ServerHost     string             `json:"server_host"`
	AppVersion     string             `json:"app_version"`
	LastSync       time.Time          `json:"last_sync"`
	RawResponse    []byte             `json:"-"`
}

// Internal raw JSON response representations from subscription APIs.
type rawSubscriptionResponse struct {
	Status       string          `json:"status"`
	Error        string          `json:"error"`
	CabinetURL   string          `json:"cabinet_url"`
	DashboardURL string          `json:"dashboard_url"`
	User         *rawUser        `json:"user"`
	Server       *rawServer      `json:"server"`
	Connections  []rawConnection `json:"connections"`
	Profiles     []rawConnection `json:"profiles"` // alternate naming
	Servers      []rawConnection `json:"servers"`  // alternate naming
}

type rawUser struct {
	ID        any    `json:"id"`
	Username  string `json:"username"`
	Role      string `json:"role"`
	ExpiresAt any    `json:"expires_at"`
}

type rawServer struct {
	Host         string `json:"host"`
	CabinetURL   string `json:"cabinet_url"`
	DashboardURL string `json:"dashboard_url"`
	AppVersion   string `json:"app_version"`
}

type rawConnection struct {
	ID            any            `json:"id"`
	Name          string         `json:"name"`
	Proto         string         `json:"proto"` // "awg", "amnezia", "amneziawg", "ocserv", "openconnect"
	Host          string         `json:"host"`
	Server        string         `json:"server"`
	Port          any            `json:"port"`
	Username      string         `json:"username"`
	Password      string         `json:"password"`
	Protocol      string         `json:"protocol"`
	ConfigContent string         `json:"config_content"`
	ConfigText    string         `json:"config_text"`
	Group         string         `json:"group"`
	Mode          string         `json:"mode"`
	URI           string         `json:"uri"`
	Camouflage    *rawCamouflage `json:"camouflage"`

	// Direct AWG fields
	IP           string `json:"ip"`
	Address      string `json:"address"`
	DNS          string `json:"dns"`
	Endpoint     string `json:"endpoint"`
	AllowedIPs   string `json:"allowed_ips"`
	PrivateKey   string `json:"private_key"`
	PublicKey    string `json:"public_key"`
	PresharedKey string `json:"preshared_key"`
	Jc           int    `json:"jc"`
	Jmin         int    `json:"jmin"`
	Jmax         int    `json:"jmax"`
	S1           int    `json:"s1"`
	S2           int    `json:"s2"`
	H1           int    `json:"h1"`
	H2           int    `json:"h2"`
	H3           int    `json:"h3"`
	H4           int    `json:"h4"`
}

type rawCamouflage struct {
	Enabled    bool   `json:"enabled"`
	Secret     string `json:"secret"`
	Path       string `json:"path"`
	ConnectURL string `json:"connect_url"`
	TLSSNI     string `json:"tls_sni"`
	DTLS       bool   `json:"dtls"`
}
