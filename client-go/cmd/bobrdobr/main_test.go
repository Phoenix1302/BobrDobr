package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/Phoenix1302/BobrDobr/pkg/config"
)

func TestAppUserModelIDInitialization(t *testing.T) {
	// Verify that calling SetCurrentProcessExplicitAppUserModelID does not panic
	SetCurrentProcessExplicitAppUserModelID("BobrDobr.VPN.Client")
	ensureAppUserModelIDRegistry()
}

func TestBuildAmneziaWGConfigText(t *testing.T) {
	cfg := &config.AmneziaWGConfig{
		Address:    "10.0.0.2/32",
		PrivateKey: "testkey",
		DNS:        "1.1.1.1",
		Endpoint:   "1.2.3.4:51820",
		PublicKey:  "pubkey",
		AllowedIPs: "0.0.0.0/0",
		Jc:         4,
		Jmin:       10,
		Jmax:       20,
	}

	text := buildAmneziaWGConfigText(cfg)
	if text == "" {
		t.Fatalf("expected non-empty config text")
	}
	if !contains(text, "Address = 10.0.0.2/32") {
		t.Errorf("missing Address")
	}
	if !contains(text, "Jc = 4") {
		t.Errorf("missing Jc")
	}
}

func TestGetAppDataDir(t *testing.T) {
	dir := getAppDataDir()
	if dir == "" {
		t.Fatalf("expected non-empty app data directory")
	}
	if !strings.HasSuffix(dir, "BobrDobr") {
		t.Errorf("expected app data dir to end with 'BobrDobr', got: %s", dir)
	}
	// Verify directory exists
	info, err := os.Stat(dir)
	if err != nil || !info.IsDir() {
		t.Errorf("expected app data directory to exist and be a directory: %v", err)
	}
}

func TestFindBinaryPath_Fallback(t *testing.T) {
	// A non-existent binary should return the input name as fallback
	nonExistent := "non_existent_engine_test_xyz123.exe"
	res := findBinaryPath(nonExistent)
	if res != nonExistent {
		t.Errorf("expected fallback to '%s', got '%s'", nonExistent, res)
	}
}

func TestFindBinaryPath_RelativeBinary(t *testing.T) {
	// If binary exists next to executable or in bin/ next to executable, it should find it
	exePath, err := os.Executable()
	if err != nil || exePath == "" {
		t.Skip("os.Executable not available")
	}
	exeDir := filepath.Dir(exePath)
	binDir := filepath.Join(exeDir, "bin")
	_ = os.MkdirAll(binDir, 0755)

	testBin := filepath.Join(binDir, "test_custom_engine.exe")
	if err := os.WriteFile(testBin, []byte("fake binary"), 0755); err != nil {
		t.Skip("failed to create fake binary for test")
	}
	defer os.Remove(testBin)

	found := findBinaryPath("test_custom_engine.exe")
	expectedAbs, _ := filepath.Abs(testBin)
	if found != expectedAbs && found != testBin {
		t.Errorf("expected to find '%s', got '%s'", expectedAbs, found)
	}
}

func TestSubscriptionExpirationLogic(t *testing.T) {
	now := time.Date(2026, 11, 11, 12, 0, 0, 0, time.UTC)

	// Case 1: Zero time (unlimited / no expiration configured)
	if isSubscriptionExpired(time.Time{}, now) {
		t.Errorf("expected zero time to NOT be expired")
	}
	daysLeft, shouldWarn := getSubscriptionDaysLeft(time.Time{}, now)
	if shouldWarn || daysLeft != 0 {
		t.Errorf("expected no warning for zero expiration time, got daysLeft=%d, shouldWarn=%v", daysLeft, shouldWarn)
	}

	// Case 2: Expired 1 day ago
	past := now.Add(-24 * time.Hour)
	if !isSubscriptionExpired(past, now) {
		t.Errorf("expected past time to be expired")
	}
	daysLeft, shouldWarn = getSubscriptionDaysLeft(past, now)
	if shouldWarn {
		t.Errorf("expected shouldWarn=false for already expired subscription")
	}

	// Case 3: Expiring soon (2 days left)
	soon := now.Add(48 * time.Hour)
	if isSubscriptionExpired(soon, now) {
		t.Errorf("expected future time to NOT be expired")
	}
	daysLeft, shouldWarn = getSubscriptionDaysLeft(soon, now)
	if !shouldWarn || daysLeft > 3 || daysLeft <= 0 {
		t.Errorf("expected expiring warning for 2 days left, got daysLeft=%d, shouldWarn=%v", daysLeft, shouldWarn)
	}

	// Case 4: Far future (30 days left)
	farFuture := now.Add(30 * 24 * time.Hour)
	if isSubscriptionExpired(farFuture, now) {
		t.Errorf("expected 30 days future to NOT be expired")
	}
	daysLeft, shouldWarn = getSubscriptionDaysLeft(farFuture, now)
	if shouldWarn {
		t.Errorf("expected shouldWarn=false for far future subscription, got daysLeft=%d", daysLeft)
	}
}

func TestCanConnectProfile_FrozenTunnel(t *testing.T) {
	now := time.Date(2026, 11, 11, 12, 0, 0, 0, time.UTC)
	expiredDate := now.Add(-10 * time.Hour)
	validDate := now.Add(10 * 24 * time.Hour)

	subProfile := config.Profile{
		ID:             "sub-prof-1",
		Name:           "Bobr Platinum NL",
		IsSubscription: true,
		Protocol:       "amnezia",
	}

	customProfile := config.Profile{
		ID:             "custom-prof-1",
		Name:           "Home WireGuard",
		IsSubscription: false,
		Protocol:       "amnezia",
	}

	// Test 1: Subscription profile with expired subscription -> MUST BE BLOCKED
	allowed, reason := canConnectProfile(subProfile, "expired", expiredDate, now)
	if allowed {
		t.Errorf("expected expired subscription profile to be blocked")
	}
	if !strings.Contains(reason, "срок действия подписки истёк") {
		t.Errorf("unexpected block reason: %s", reason)
	}

	// Test 1b: Subscription profile with expired date even if subStatus is "" -> MUST BE BLOCKED
	allowed, reason = canConnectProfile(subProfile, "", expiredDate, now)
	if allowed {
		t.Errorf("expected expired subscription profile by date to be blocked")
	}
	if !strings.Contains(reason, "срок действия подписки истёк") {
		t.Errorf("unexpected block reason: %s", reason)
	}

	// Test 1c: Subscription profile with status "blocked" -> MUST BE BLOCKED
	allowed, reason = canConnectProfile(subProfile, "blocked", validDate, now)
	if allowed {
		t.Errorf("expected blocked subscription profile to be blocked even with valid date")
	}
	if !strings.Contains(reason, "ваш аккаунт заблокирован администратором") {
		t.Errorf("unexpected block reason: %s", reason)
	}

	// Test 1d: Subscription profile with status "revoked" -> MUST BE BLOCKED
	allowed, reason = canConnectProfile(subProfile, "revoked", validDate, now)
	if allowed {
		t.Errorf("expected revoked subscription profile to be blocked")
	}
	if !strings.Contains(reason, "токен подписки недействителен или был удален") {
		t.Errorf("unexpected block reason: %s", reason)
	}

	// Test 2: Subscription profile with active subscription -> ALLOWED
	allowed, reason = canConnectProfile(subProfile, "active", validDate, now)
	if !allowed || reason != "" {
		t.Errorf("expected valid subscription profile to be allowed, got allowed=%v, reason=%s", allowed, reason)
	}

	// Test 3: Subscription profile with zero expiration date (perpetual) -> ALLOWED
	allowed, reason = canConnectProfile(subProfile, "active", time.Time{}, now)
	if !allowed || reason != "" {
		t.Errorf("expected perpetual subscription profile to be allowed, got allowed=%v, reason=%s", allowed, reason)
	}

	// Test 4: Custom profile even when subscription is expired/blocked -> MUST REMAIN ALLOWED
	allowed, reason = canConnectProfile(customProfile, "blocked", expiredDate, now)
	if !allowed {
		t.Errorf("expected custom user profile to ALWAYS be allowed even if subscription expired or blocked")
	}
}

func contains(s, substr string) bool {
	return len(s) >= len(substr) && (s == substr || len(s) > 0 && searchSubstring(s, substr))
}

func searchSubstring(s, substr string) bool {
	for i := 0; i+len(substr) <= len(s); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}
