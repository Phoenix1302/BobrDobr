package subscription

import (
	"context"
	"encoding/base64"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Phoenix1302/BobrDobr/pkg/config"
)

func TestParseValidSubscriptionResponse(t *testing.T) {
	futureTime := time.Now().Add(30 * 24 * time.Hour).UTC().Format(time.RFC3339)

	jsonPayload := fmt.Sprintf(`{
		"status": "active",
		"cabinet_url": "https://persona.netphoenix.ru",
		"user": {
			"id": 42,
			"username": "Egor",
			"role": "vip",
			"expires_at": "%s"
		},
		"server": {
			"host": "persona.netphoenix.ru",
			"app_version": "1.1.0"
		},
		"connections": [
			{
				"id": "awg-101",
				"name": "Egor_awg1",
				"proto": "awg",
				"config_content": "[Interface]\nAddress = 10.8.0.2/32\nPrivateKey = aW5pdGlhbC1wcml2YXRlLWtleS0zMi1ieXRlcw==\nDNS = 1.1.1.1\nJc = 4\nJmin = 40\nJmax = 70\nS1 = 15\nS2 = 30\nH1 = 11\nH2 = 22\nH3 = 33\nH4 = 44\n\n[Peer]\nPublicKey = cGVlci1wdWJsaWMta2V5LTMyLWJ5dGVzLTEyMzQ1Ng==\nEndpoint = awg.vpn.net:51820\nAllowedIPs = 0.0.0.0/0\n"
			},
			{
				"id": "oc-202",
				"name": "Egor_oc1 -SUB",
				"proto": "ocserv",
				"server": "oc.vpn.net",
				"port": 443,
				"username": "beaver",
				"password": "dam-password",
				"protocol": "anyconnect",
				"camouflage": {
					"enabled": true,
					"secret": "river_secret"
				}
			}
		]
	}`, futureTime)

	info, err := DecodeSubscriptionPayload([]byte(jsonPayload), "https://persona.netphoenix.ru/api/v1/sub/testtoken", "")
	if err != nil {
		t.Fatalf("failed to decode valid subscription: %v", err)
	}

	if info.CabinetURL != "https://persona.netphoenix.ru" {
		t.Fatalf("expected cabinet URL 'https://persona.netphoenix.ru', got '%s'", info.CabinetURL)
	}
	if info.UserID != "42" {
		t.Fatalf("expected user ID '42', got '%s'", info.UserID)
	}
	if info.Username != "Egor" {
		t.Fatalf("expected username 'Egor', got '%s'", info.Username)
	}
	if !info.IsActive {
		t.Fatalf("expected subscription to be active")
	}
	if info.IsExpired || info.IsFrozen {
		t.Fatalf("expected active subscription to not be expired or frozen")
	}
	if info.DaysLeft <= 25 {
		t.Fatalf("expected ~30 days left, got %d", info.DaysLeft)
	}

	// Verify Profiles
	if len(info.Profiles) != 2 {
		t.Fatalf("expected 2 profiles, got %d", len(info.Profiles))
	}

	// Profile 1: AWG
	p1 := info.Profiles[0]
	if p1.Name != "Egor_awg1-sub" {
		t.Fatalf("expected profile name 'Egor_awg1-sub', got '%s'", p1.Name)
	}
	if p1.Protocol != config.ProtocolAmneziaWG {
		t.Fatalf("expected protocol '%s', got '%s'", config.ProtocolAmneziaWG, p1.Protocol)
	}
	if p1.Server != "awg.vpn.net" || p1.Port != 51820 {
		t.Fatalf("expected server 'awg.vpn.net:51820', got '%s:%d'", p1.Server, p1.Port)
	}
	if p1.AmneziaConfig == nil {
		t.Fatalf("expected non-nil AmneziaConfig")
	}
	if p1.AmneziaConfig.Jc != 4 || p1.AmneziaConfig.Jmin != 40 || p1.AmneziaConfig.Jmax != 70 {
		t.Fatalf("unexpected obfuscation junk values: %+v", p1.AmneziaConfig)
	}
	if p1.AmneziaConfig.H1 != 11 || p1.AmneziaConfig.H4 != 44 {
		t.Fatalf("unexpected obfuscation headers: %+v", p1.AmneziaConfig)
	}

	// Profile 2: OpenConnect
	p2 := info.Profiles[1]
	if p2.Name != "Egor_oc1-sub" {
		t.Fatalf("expected formatted name 'Egor_oc1-sub', got '%s'", p2.Name)
	}
	if p2.Protocol != config.ProtocolOpenConnect {
		t.Fatalf("expected protocol '%s', got '%s'", config.ProtocolOpenConnect, p2.Protocol)
	}
	if p2.OpenConnect == nil {
		t.Fatalf("expected non-nil OpenConnect config")
	}
	if p2.OpenConnect.Password != "dam-password" {
		t.Fatalf("expected password 'dam-password', got '%s'", p2.OpenConnect.Password)
	}
	if p2.OpenConnect.Server != "oc.vpn.net/?river_secret" {
		t.Fatalf("expected camouflage URL in server, got '%s'", p2.OpenConnect.Server)
	}
}

func TestParseExpiredAndFrozenSubscription(t *testing.T) {
	pastTime := time.Now().Add(-48 * time.Hour).UTC().Format(time.RFC3339)

	// Past expiry date
	jsonPayload := fmt.Sprintf(`{
		"status": "active",
		"user": {
			"username": "ExpiredUser",
			"expires_at": "%s"
		},
		"connections": [
			{
				"id": "1",
				"name": "AWG",
				"proto": "awg",
				"endpoint": "vpn.net:51820"
			}
		]
	}`, pastTime)

	info, err := DecodeSubscriptionPayload([]byte(jsonPayload), "https://persona.netphoenix.ru", "")
	if err != nil {
		t.Fatalf("failed to decode: %v", err)
	}

	if !info.IsExpired {
		t.Fatalf("expected subscription to be marked expired")
	}
	if !info.IsFrozen {
		t.Fatalf("expected subscription to be marked frozen")
	}
	if info.IsActive {
		t.Fatalf("expected expired subscription to not be active")
	}
	if info.DaysLeft != 0 {
		t.Fatalf("expected 0 days left, got %d", info.DaysLeft)
	}

	// Blocked status
	blockedPayload := `{
		"status": "blocked",
		"user": { "username": "BadUser" },
		"connections": []
	}`
	bInfo, err := DecodeSubscriptionPayload([]byte(blockedPayload), "https://persona.netphoenix.ru", "")
	if err != nil {
		t.Fatalf("failed to decode: %v", err)
	}
	if !bInfo.IsFrozen {
		t.Fatalf("expected blocked subscription to be frozen")
	}
	if bInfo.IsActive {
		t.Fatalf("expected blocked subscription to not be active")
	}
	if bInfo.Status != StatusBlocked {
		t.Fatalf("expected status 'blocked', got '%s'", bInfo.Status)
	}
}

func TestParseBase64EncodedPayload(t *testing.T) {
	jsonContent := `{
		"status": "active",
		"connections": [
			{
				"id": "b64-1",
				"name": "B64AWG",
				"proto": "awg",
				"endpoint": "b64.vpn.org:51820",
				"jc": 3,
				"jmin": 10,
				"jmax": 20
			}
		]
	}`

	b64Encoded := base64.StdEncoding.EncodeToString([]byte(jsonContent))

	info, err := DecodeSubscriptionPayload([]byte(b64Encoded), "https://persona.netphoenix.ru/api/v1/sub/b64", "")
	if err != nil {
		t.Fatalf("failed to parse base64 payload: %v", err)
	}

	if len(info.Profiles) != 1 {
		t.Fatalf("expected 1 profile, got %d", len(info.Profiles))
	}
	if info.Profiles[0].Name != "B64AWG-sub" {
		t.Fatalf("expected name 'B64AWG-sub', got '%s'", info.Profiles[0].Name)
	}

	// Test raw WireGuard config in base64
	rawConf := "[Interface]\nAddress = 10.0.0.1/32\nPrivateKey = testkey\n[Peer]\nEndpoint = raw.vpn.org:51820\n"
	b64Conf := base64.StdEncoding.EncodeToString([]byte(rawConf))

	rawInfo, err := DecodeSubscriptionPayload([]byte(b64Conf), "https://custom.vpn/sub", "")
	if err != nil {
		t.Fatalf("failed to parse base64 raw conf: %v", err)
	}
	if len(rawInfo.Profiles) != 1 {
		t.Fatalf("expected 1 profile from raw conf, got %d", len(rawInfo.Profiles))
	}
	if rawInfo.Profiles[0].Server != "raw.vpn.org" {
		t.Fatalf("expected server 'raw.vpn.org', got '%s'", rawInfo.Profiles[0].Server)
	}
}

func TestParseMalformedInputs(t *testing.T) {
	// Empty input
	_, err := DecodeSubscriptionPayload([]byte(""), "https://persona.netphoenix.ru", "")
	if err != ErrEmptyPayload {
		t.Fatalf("expected ErrEmptyPayload, got %v", err)
	}

	// Whitespace only
	_, err = DecodeSubscriptionPayload([]byte("   \n\t  "), "https://persona.netphoenix.ru", "")
	if err != ErrEmptyPayload {
		t.Fatalf("expected ErrEmptyPayload, got %v", err)
	}

	// Invalid characters / corrupted non-json non-conf
	_, err = DecodeSubscriptionPayload([]byte("@@!!$$__NOT_A_VALID_CONFIG_OR_JSON__"), "https://persona.netphoenix.ru", "")
	if err == nil {
		t.Fatalf("expected error on malformed input, got nil")
	}
}

func TestDynamicCabinetURLDiscovery(t *testing.T) {
	// Case 1: Explicit cabinet_url in JSON takes highest priority
	jsonWithCab := `{"cabinet_url": "https://explicit.lk.net", "connections": []}`
	info1, err := DecodeSubscriptionPayload([]byte(jsonWithCab), "https://persona.netphoenix.ru/sub/123", "")
	if err != nil {
		t.Fatalf("failed decode: %v", err)
	}
	if info1.CabinetURL != "https://explicit.lk.net" {
		t.Fatalf("expected 'https://explicit.lk.net', got '%s'", info1.CabinetURL)
	}

	// Case 2: Extract from subscription URL host
	jsonNoCab := `{"status": "active", "connections": []}`
	info2, err := DecodeSubscriptionPayload([]byte(jsonNoCab), "https://my-custom-host.com:8443/api/v1/sub/token", "")
	if err != nil {
		t.Fatalf("failed decode: %v", err)
	}
	if info2.CabinetURL != "https://my-custom-host.com:8443/cloud" {
		t.Fatalf("expected 'https://my-custom-host.com:8443/cloud', got '%s'", info2.CabinetURL)
	}

	// Case 3: Fallback default
	info3, err := DecodeSubscriptionPayload([]byte(jsonNoCab), "", "")
	if err != nil {
		t.Fatalf("failed decode: %v", err)
	}
	if info3.CabinetURL != "https://example.com/cloud" {
		t.Fatalf("expected fallback default 'https://example.com/cloud', got '%s'", info3.CabinetURL)
	}
}

func TestProfileNameFormatting(t *testing.T) {
	cases := []struct {
		input    string
		expected string
	}{
		{"Egor_awg1", "Egor_awg1-sub"},
		{"Egor_awg1 -SUB", "Egor_awg1-sub"},
		{"Egor_awg1-SUB", "Egor_awg1-sub"},
		{"Egor_awg1 -sub", "Egor_awg1-sub"},
		{"Egor_awg1-sub", "Egor_awg1-sub"},
		{"Egor_awg1 - Sub", "Egor_awg1-sub"},
		{"", "vpn-sub"},
		{"   ", "vpn-sub"},
		{"-sub", "vpn-sub"},
	}

	for _, c := range cases {
		result := FormatSubscriptionProfileName(c.input)
		if result != c.expected {
			t.Errorf("FormatSubscriptionProfileName(%q) = %q, expected %q", c.input, result, c.expected)
		}
	}
}

func TestHTTPClientWithMockServer(t *testing.T) {
	var requestCount int32

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		count := atomic.AddInt32(&requestCount, 1)

		// First request triggers HTTP 429 to test backoff and retry
		if count == 1 {
			w.Header().Set("Retry-After", "0")
			w.WriteHeader(http.StatusTooManyRequests)
			_, _ = w.Write([]byte(`{"error": "rate limited"}`))
			return
		}

		// Second request succeeds
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("Subscription-Userinfo", "upload=100; download=200; total=300; expire=1893456000")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{
			"status": "active",
			"connections": [
				{
					"id": "1",
					"name": "Server1",
					"proto": "awg",
					"endpoint": "test.vpn:51820"
				}
			]
		}`))
	}))
	defer server.Close()

	client := NewClient(
		WithTimeout(5*time.Second),
		WithMaxRetries(2),
	)

	ctx := context.Background()
	info, err := client.FetchSubscription(ctx, server.URL)
	if err != nil {
		t.Fatalf("expected successful fetch after retry, got: %v", err)
	}

	if len(info.Profiles) != 1 {
		t.Fatalf("expected 1 profile, got %d", len(info.Profiles))
	}
	if atomic.LoadInt32(&requestCount) != 2 {
		t.Fatalf("expected 2 requests (1 retry), got %d", atomic.LoadInt32(&requestCount))
	}

	// Verify expiration was parsed from Subscription-Userinfo header
	if info.ExpiresAt.Unix() != 1893456000 {
		t.Fatalf("expected expires_at 1893456000, got %d", info.ExpiresAt.Unix())
	}
}

func TestHTTPClientErrorCodes(t *testing.T) {
	// 401 Unauthorized
	s401 := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusUnauthorized)
		_, _ = w.Write([]byte(`{"error": "Invalid or revoked token"}`))
	}))
	defer s401.Close()

	client := NewClient()
	_, err := client.FetchSubscription(context.Background(), s401.URL)
	if !IsRevoked(err) {
		t.Fatalf("expected IsRevoked(err) == true, got: %v", err)
	}
	var srvErr *ServerError
	if !errors.As(err, &srvErr) || srvErr.Code != CodeTokenRevoked {
		t.Fatalf("expected CodeTokenRevoked, got: %+v", srvErr)
	}
	if !errors.Is(err, ErrUnauthorized) {
		t.Fatalf("expected errors.Is(err, ErrUnauthorized) == true")
	}

	// 404 Not Found
	s404 := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer s404.Close()

	_, err = client.FetchSubscription(context.Background(), s404.URL)
	if err != ErrNotFound {
		t.Fatalf("expected ErrNotFound, got: %v", err)
	}

	// 403 Forbidden (Blocked)
	s403 := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusForbidden)
		_, _ = w.Write([]byte(`{"error": "Account is blocked by administrator"}`))
	}))
	defer s403.Close()

	_, err = client.FetchSubscription(context.Background(), s403.URL)
	if !IsBlocked(err) {
		t.Fatalf("expected IsBlocked(err) == true, got %v", err)
	}
	if !errors.As(err, &srvErr) || srvErr.Code != CodeAccountBlocked {
		t.Fatalf("expected CodeAccountBlocked, got: %+v", srvErr)
	}
}

func TestServerError403AccountBlocked(t *testing.T) {
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusForbidden)
		_, _ = w.Write([]byte(`{"error": "Account is blocked by administrator"}`))
	}))
	defer s.Close()

	client := NewClient()
	info, err := client.FetchSubscription(context.Background(), s.URL+"/api/v1/sub/mytoken")
	if info != nil {
		t.Fatalf("expected nil info on blocked error, got %+v", info)
	}
	if err == nil {
		t.Fatalf("expected error on blocked account")
	}

	if !IsBlocked(err) {
		t.Fatalf("expected IsBlocked(err) == true")
	}
	if IsExpired(err) || IsRevoked(err) || IsRateLimited(err) {
		t.Fatalf("expected only IsBlocked to be true")
	}

	var srvErr *ServerError
	if !errors.As(err, &srvErr) {
		t.Fatalf("expected error to match *ServerError via errors.As")
	}

	if srvErr.StatusCode != 403 {
		t.Errorf("expected StatusCode 403, got %d", srvErr.StatusCode)
	}
	if srvErr.Code != CodeAccountBlocked {
		t.Errorf("expected Code %s, got %s", CodeAccountBlocked, srvErr.Code)
	}
	expectedMsg := "Ваш аккаунт заблокирован администратором. Обратитесь в поддержку."
	if srvErr.Message != expectedMsg {
		t.Errorf("expected Message %q, got %q", expectedMsg, srvErr.Message)
	}
	if !strings.HasSuffix(srvErr.CabinetURL, "/cloud") {
		t.Errorf("expected CabinetURL to end with /cloud, got %q", srvErr.CabinetURL)
	}
	if !strings.Contains(srvErr.RawBody, "Account is blocked by administrator") {
		t.Errorf("expected RawBody to contain response body, got %q", srvErr.RawBody)
	}
}

func TestServerError403SubscriptionExpired(t *testing.T) {
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusForbidden)
		_, _ = w.Write([]byte(`{"error": "Subscription expired. Please renew access."}`))
	}))
	defer s.Close()

	client := NewClient()
	info, err := client.FetchSubscription(context.Background(), s.URL+"/sub/mytoken")
	if info != nil {
		t.Fatalf("expected nil info on expired error, got %+v", info)
	}
	if err == nil {
		t.Fatalf("expected error on expired subscription")
	}

	if !IsExpired(err) {
		t.Fatalf("expected IsExpired(err) == true")
	}
	if IsBlocked(err) || IsRevoked(err) || IsRateLimited(err) {
		t.Fatalf("expected only IsExpired to be true")
	}

	var srvErr *ServerError
	if !errors.As(err, &srvErr) {
		t.Fatalf("expected error to match *ServerError via errors.As")
	}

	if srvErr.StatusCode != 403 {
		t.Errorf("expected StatusCode 403, got %d", srvErr.StatusCode)
	}
	if srvErr.Code != CodeSubExpired {
		t.Errorf("expected Code %s, got %s", CodeSubExpired, srvErr.Code)
	}
	expectedMsg := "Срок действия подписки истек. Продлите доступ в личном кабинете веб-панели."
	if srvErr.Message != expectedMsg {
		t.Errorf("expected Message %q, got %q", expectedMsg, srvErr.Message)
	}
	if !strings.HasSuffix(srvErr.CabinetURL, "/cloud") {
		t.Errorf("expected CabinetURL to end with /cloud, got %q", srvErr.CabinetURL)
	}
	if !strings.Contains(srvErr.RawBody, "Subscription expired") {
		t.Errorf("expected RawBody to contain response body, got %q", srvErr.RawBody)
	}
}

func TestServerError401TokenRevoked(t *testing.T) {
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusUnauthorized)
		_, _ = w.Write([]byte(`{"error": "Invalid or revoked token"}`))
	}))
	defer s.Close()

	client := NewClient()
	info, err := client.FetchSubscription(context.Background(), s.URL+"/api/v1/sub/revokedtoken")
	if info != nil {
		t.Fatalf("expected nil info on revoked error, got %+v", info)
	}
	if err == nil {
		t.Fatalf("expected error on revoked token")
	}

	if !IsRevoked(err) {
		t.Fatalf("expected IsRevoked(err) == true")
	}
	if IsBlocked(err) || IsExpired(err) || IsRateLimited(err) {
		t.Fatalf("expected only IsRevoked to be true")
	}

	var srvErr *ServerError
	if !errors.As(err, &srvErr) {
		t.Fatalf("expected error to match *ServerError via errors.As")
	}

	if srvErr.StatusCode != 401 {
		t.Errorf("expected StatusCode 401, got %d", srvErr.StatusCode)
	}
	if srvErr.Code != CodeTokenRevoked {
		t.Errorf("expected Code %s, got %s", CodeTokenRevoked, srvErr.Code)
	}
	expectedMsg := "Токен подписки недействителен или был удален. Скопируйте новую ссылку в веб-панели."
	if srvErr.Message != expectedMsg {
		t.Errorf("expected Message %q, got %q", expectedMsg, srvErr.Message)
	}
	if !strings.HasSuffix(srvErr.CabinetURL, "/cloud") {
		t.Errorf("expected CabinetURL to end with /cloud, got %q", srvErr.CabinetURL)
	}
}

func TestServerError429RateLimited(t *testing.T) {
	var attempts int32
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&attempts, 1)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusTooManyRequests)
		_, _ = w.Write([]byte(`{"error": "Rate limit exceeded. Try again later."}`))
	}))
	defer s.Close()

	// Fast retry delays to avoid waiting 5s + 15s + 60s in tests
	client := NewClient(
		WithRetryDelays(1*time.Millisecond, 2*time.Millisecond),
	)

	info, err := client.FetchSubscription(context.Background(), s.URL+"/sub/ratelimited")
	if info != nil {
		t.Fatalf("expected nil info on rate limit error, got %+v", info)
	}
	if err == nil {
		t.Fatalf("expected error on rate limit")
	}

	if !IsRateLimited(err) {
		t.Fatalf("expected IsRateLimited(err) == true")
	}
	if IsBlocked(err) || IsExpired(err) || IsRevoked(err) {
		t.Fatalf("expected only IsRateLimited to be true")
	}

	var srvErr *ServerError
	if !errors.As(err, &srvErr) {
		t.Fatalf("expected error to match *ServerError via errors.As")
	}

	if srvErr.StatusCode != 429 {
		t.Errorf("expected StatusCode 429, got %d", srvErr.StatusCode)
	}
	if srvErr.Code != CodeRateLimited {
		t.Errorf("expected Code %s, got %s", CodeRateLimited, srvErr.Code)
	}
	if !strings.Contains(srvErr.Message, "Rate limit exceeded") {
		t.Errorf("expected rate limit message, got %q", srvErr.Message)
	}
	if !strings.HasSuffix(srvErr.CabinetURL, "/cloud") {
		t.Errorf("expected CabinetURL to end with /cloud, got %q", srvErr.CabinetURL)
	}
	// Verify that initial request + 2 retries were performed (3 attempts total)
	if atomic.LoadInt32(&attempts) != 3 {
		t.Errorf("expected 3 attempts, got %d", atomic.LoadInt32(&attempts))
	}
}

func Test200OKWithIsFrozen(t *testing.T) {
	// Case 1: is_frozen == 2 in top-level JSON body -> StatusBlocked
	jsonBlocked := `{
		"status": "active",
		"is_frozen": 2,
		"connections": []
	}`
	info1, err := DecodeSubscriptionPayload([]byte(jsonBlocked), "https://persona.netphoenix.ru/sub/tok", "")
	if err != nil {
		t.Fatalf("unexpected decode error: %v", err)
	}
	if info1.Status != StatusBlocked {
		t.Errorf("expected status %s, got %s", StatusBlocked, info1.Status)
	}
	if !info1.IsFrozen {
		t.Errorf("expected IsFrozen == true")
	}
	if info1.IsActive {
		t.Errorf("expected IsActive == false")
	}

	// Case 2: is_frozen == 1 in top-level JSON body -> StatusExpired, IsExpired = true, IsFrozen = true
	jsonExpired := `{
		"status": "active",
		"is_frozen": 1,
		"connections": []
	}`
	info2, err := DecodeSubscriptionPayload([]byte(jsonExpired), "https://persona.netphoenix.ru/sub/tok", "")
	if err != nil {
		t.Fatalf("unexpected decode error: %v", err)
	}
	if info2.Status != StatusExpired {
		t.Errorf("expected status %s, got %s", StatusExpired, info2.Status)
	}
	if !info2.IsExpired {
		t.Errorf("expected IsExpired == true")
	}
	if !info2.IsFrozen {
		t.Errorf("expected IsFrozen == true")
	}
	if info2.IsActive {
		t.Errorf("expected IsActive == false")
	}

	// Case 3: is_frozen == 2 in user object -> StatusBlocked
	jsonUserBlocked := `{
		"status": "active",
		"user": {
			"username": "BlockedUser",
			"is_frozen": 2
		},
		"connections": []
	}`
	info3, err := DecodeSubscriptionPayload([]byte(jsonUserBlocked), "https://persona.netphoenix.ru/sub/tok", "")
	if err != nil {
		t.Fatalf("unexpected decode error: %v", err)
	}
	if info3.Status != StatusBlocked {
		t.Errorf("expected status %s, got %s", StatusBlocked, info3.Status)
	}
	if !info3.IsFrozen {
		t.Errorf("expected IsFrozen == true")
	}

	// Case 4: is_frozen == 1 in user object -> StatusExpired
	jsonUserExpired := `{
		"status": "active",
		"user": {
			"username": "ExpiredUser",
			"is_frozen": 1
		},
		"connections": []
	}`
	info4, err := DecodeSubscriptionPayload([]byte(jsonUserExpired), "https://persona.netphoenix.ru/sub/tok", "")
	if err != nil {
		t.Fatalf("unexpected decode error: %v", err)
	}
	if info4.Status != StatusExpired {
		t.Errorf("expected status %s, got %s", StatusExpired, info4.Status)
	}
	if !info4.IsExpired || !info4.IsFrozen {
		t.Errorf("expected IsExpired and IsFrozen to be true")
	}

	// Case 5: String representation "is_frozen": "2"
	jsonStringBlocked := `{
		"status": "active",
		"is_frozen": "2",
		"connections": []
	}`
	info5, err := DecodeSubscriptionPayload([]byte(jsonStringBlocked), "https://persona.netphoenix.ru/sub/tok", "")
	if err != nil {
		t.Fatalf("unexpected decode error: %v", err)
	}
	if info5.Status != StatusBlocked {
		t.Errorf("expected status %s, got %s", StatusBlocked, info5.Status)
	}
}

func TestValidateSubscriptionURL(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status": "active", "connections": [{"id": "1", "name": "V", "proto": "awg", "endpoint": "1.2.3.4:51820"}]}`))
	}))
	defer server.Close()

	client := NewClient()

	// Valid URL
	if err := client.ValidateSubscriptionURL(context.Background(), server.URL); err != nil {
		t.Fatalf("expected valid URL to succeed, got %v", err)
	}

	// Empty URL
	if err := client.ValidateSubscriptionURL(context.Background(), ""); err != ErrEmptyURL {
		t.Fatalf("expected ErrEmptyURL, got %v", err)
	}

	// Invalid URL scheme / format
	if err := client.ValidateSubscriptionURL(context.Background(), "://invalid-url-format"); err == nil {
		t.Fatalf("expected error for invalid URL")
	}
}
