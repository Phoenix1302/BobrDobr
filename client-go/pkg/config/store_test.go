package config

import (
	"encoding/base64"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

// Helper to generate a valid WireGuard 32-byte base64 key
func testWGKey() string {
	b := make([]byte, 32)
	for i := range b {
		b[i] = byte(i + 1)
	}
	return base64.StdEncoding.EncodeToString(b)
}

func TestAESGCMEncryptionRoundtrip(t *testing.T) {
	seed := []byte("test-super-secret-seed-1234567890")
	encryptor := NewAESGCMEncryptor(seed)

	originalData := []byte(`{"user":"bobr","action":"build_dam","enabled":true}`)

	envelope, err := encryptor.Encrypt(originalData)
	if err != nil {
		t.Fatalf("encryption failed: %v", err)
	}

	if envelope.Encryption != EncryptionAES256GCM {
		t.Fatalf("expected encryption algorithm %s, got %s", EncryptionAES256GCM, envelope.Encryption)
	}
	if envelope.Salt == "" || envelope.Nonce == "" || envelope.Data == "" {
		t.Fatalf("expected non-empty salt, nonce, and data")
	}

	// Decrypt
	decrypted, err := encryptor.Decrypt(envelope)
	if err != nil {
		t.Fatalf("decryption failed: %v", err)
	}

	if string(decrypted) != string(originalData) {
		t.Fatalf("expected %s, got %s", string(originalData), string(decrypted))
	}
}

func TestAESGCMTamperDetection(t *testing.T) {
	seed := []byte("test-tamper-seed")
	encryptor := NewAESGCMEncryptor(seed)

	envelope, err := encryptor.Encrypt([]byte("confidential payload"))
	if err != nil {
		t.Fatalf("encrypt failed: %v", err)
	}

	// Tamper with data ciphertext bytes
	dataBytes, _ := base64.StdEncoding.DecodeString(envelope.Data)
	dataBytes[len(dataBytes)-1] ^= 0xFF // Flip last byte (in GCM this corrupts the auth tag)
	envelope.Data = base64.StdEncoding.EncodeToString(dataBytes)

	_, err = encryptor.Decrypt(envelope)
	if err == nil {
		t.Fatalf("expected decryption error on tampered ciphertext, got nil")
	}
}

func TestStoreCRUDAndAtomicSave(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "bobr_store_test_*")
	if err != nil {
		t.Fatalf("failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	filePath := filepath.Join(tmpDir, "settings.json")
	store, err := NewStore(filePath)
	if err != nil {
		t.Fatalf("failed to init store: %v", err)
	}

	// Test default settings
	settings, err := store.GetSettings()
	if err != nil {
		t.Fatalf("failed to get settings: %v", err)
	}
	if settings.Theme != "dark" || settings.Language != "ru" {
		t.Fatalf("unexpected default settings: %+v", settings)
	}

	// Update settings
	settings.Theme = "light"
	settings.AutoConnect = true
	settings.KillSwitch = true
	settings.SubscriptionURL = "https://persona.netphoenix.ru/api/v1/sub/testtoken"
	if err := store.SaveSettings(settings); err != nil {
		t.Fatalf("failed to save settings: %v", err)
	}

	// Verify file was written
	if _, err := os.Stat(filePath); err != nil {
		t.Fatalf("settings.json was not created: %v", err)
	}

	// Create an AmneziaWG profile
	key := testWGKey()
	awgProfile := Profile{
		Name:     "Amnezia Office",
		Protocol: ProtocolAmneziaWG,
		Server:   "vpn.example.com",
		Port:     51820,
		AmneziaConfig: &AmneziaWGConfig{
			Address:    "10.8.0.2/32",
			PrivateKey: key,
			PublicKey:  key,
			Endpoint:   "vpn.example.com:51820",
			AllowedIPs: "0.0.0.0/0",
			Jc:         4,
			Jmin:       40,
			Jmax:       70,
			S1:         15,
			S2:         30,
			H1:         1,
			H2:         2,
			H3:         3,
			H4:         4,
		},
	}

	if err := store.SaveProfile(awgProfile); err != nil {
		t.Fatalf("failed to save awg profile: %v", err)
	}

	// Create an OpenConnect profile
	ocProfile := Profile{
		Name:     "OpenConnect DC",
		Protocol: ProtocolOpenConnect,
		Server:   "oc.example.com",
		Port:     443,
		OpenConnect: &OpenConnectConfig{
			Server:   "oc.example.com",
			Port:     443,
			Username: "beaver",
			Password: "dam-password",
			Protocol: "anyconnect",
		},
	}

	if err := store.SaveProfile(ocProfile); err != nil {
		t.Fatalf("failed to save oc profile: %v", err)
	}

	// List profiles
	profiles, err := store.ListProfiles()
	if err != nil {
		t.Fatalf("failed to list profiles: %v", err)
	}
	if len(profiles) != 2 {
		t.Fatalf("expected 2 profiles, got %d", len(profiles))
	}

	// Verify IDs were assigned
	p1 := profiles[0]
	if p1.ID == "" {
		t.Fatalf("expected auto-assigned UUID for profile 1")
	}

	// Get Profile
	retrieved, err := store.GetProfile(p1.ID)
	if err != nil {
		t.Fatalf("failed to get profile by id: %v", err)
	}
	if retrieved.Name != p1.Name {
		t.Fatalf("expected profile name %s, got %s", p1.Name, retrieved.Name)
	}

	// Update existing profile
	p1.Name = "Updated Amnezia Office"
	if err := store.SaveProfile(p1); err != nil {
		t.Fatalf("failed to update profile: %v", err)
	}
	updated, _ := store.GetProfile(p1.ID)
	if updated.Name != "Updated Amnezia Office" {
		t.Fatalf("expected updated name, got %s", updated.Name)
	}

	// Reopen store from disk and check persistence
	store2, err := NewStore(filePath)
	if err != nil {
		t.Fatalf("failed to reopen store: %v", err)
	}
	s2Settings, _ := store2.GetSettings()
	if s2Settings.Theme != "light" || !s2Settings.AutoConnect {
		t.Fatalf("settings not properly persisted: %+v", s2Settings)
	}
	s2Profiles, _ := store2.ListProfiles()
	if len(s2Profiles) != 2 {
		t.Fatalf("expected 2 profiles after reload, got %d", len(s2Profiles))
	}

	// Delete profile
	if err := store2.DeleteProfile(p1.ID); err != nil {
		t.Fatalf("failed to delete profile: %v", err)
	}
	s2ProfilesAfter, _ := store2.ListProfiles()
	if len(s2ProfilesAfter) != 1 {
		t.Fatalf("expected 1 profile after delete, got %d", len(s2ProfilesAfter))
	}

	// Verify ErrProfileNotFound
	_, err = store2.GetProfile(p1.ID)
	if err != ErrProfileNotFound {
		t.Fatalf("expected ErrProfileNotFound, got %v", err)
	}
}

func TestBackupFallbackOnCorruption(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "bobr_backup_test_*")
	if err != nil {
		t.Fatalf("failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	filePath := filepath.Join(tmpDir, "settings.json")
	bakPath := filepath.Join(tmpDir, "settings.json.bak")

	store, err := NewStore(filePath)
	if err != nil {
		t.Fatalf("failed to init store: %v", err)
	}

	// Save initial settings
	settings, _ := store.GetSettings()
	settings.Theme = "light"
	settings.SubscriptionURL = "https://persona.netphoenix.ru/api/v1/sub/initial"
	_ = store.SaveSettings(settings)

	// Save a profile so second write creates .bak containing valid initial state
	key := testWGKey()
	_ = store.SaveProfile(Profile{
		Name:     "TestProfile",
		Protocol: ProtocolAmneziaWG,
		Server:   "vpn.test.com",
		Port:     51820,
		AmneziaConfig: &AmneziaWGConfig{
			Address:    "10.8.0.2/32",
			PrivateKey: key,
			PublicKey:  key,
			Endpoint:   "vpn.test.com:51820",
		},
	})

	// Verify .bak exists and has valid data
	if _, err := os.Stat(bakPath); err != nil {
		t.Fatalf("expected backup file %s to exist: %v", bakPath, err)
	}

	// Corrupt settings.json with invalid garbage
	if err := os.WriteFile(filePath, []byte("INVALID_TRUNCATED_JSON_GARBAGE{{{"), 0600); err != nil {
		t.Fatalf("failed to write corrupted file: %v", err)
	}

	// Now reopen store - it must detect corruption in settings.json and recover from settings.json.bak
	recoveredStore, err := NewStore(filePath)
	if err != nil {
		t.Fatalf("store failed to recover from backup: %v", err)
	}

	recSettings, err := recoveredStore.GetSettings()
	if err != nil {
		t.Fatalf("failed to get recovered settings: %v", err)
	}
	if recSettings.Theme != "light" {
		t.Fatalf("expected recovered theme 'light', got '%s'", recSettings.Theme)
	}
}

func TestStoreFailsWhenBothFilesCorrupted(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "bobr_corrupt_both_*")
	if err != nil {
		t.Fatalf("failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	filePath := filepath.Join(tmpDir, "settings.json")
	bakPath := filepath.Join(tmpDir, "settings.json.bak")

	_ = os.WriteFile(filePath, []byte("GARBAGE1"), 0600)
	_ = os.WriteFile(bakPath, []byte("GARBAGE2"), 0600)

	_, err = NewStore(filePath)
	if err == nil {
		t.Fatalf("expected error when both main and backup files are corrupted, got nil")
	}
}

func TestValidationEdgeCases(t *testing.T) {
	key := testWGKey()

	// 1. AmneziaWG validation
	// Jmax < Jmin
	badAWG := &AmneziaWGConfig{
		PrivateKey: key,
		PublicKey:  key,
		Endpoint:   "vpn.net:51820",
		Jc:         2,
		Jmin:       100,
		Jmax:       50, // invalid: Jmax < Jmin
	}
	if err := badAWG.Validate(); err == nil {
		t.Fatalf("expected error for Jmax < Jmin")
	}

	// Negative junk parameter
	badJc := &AmneziaWGConfig{
		PrivateKey: key,
		PublicKey:  key,
		Endpoint:   "vpn.net:51820",
		Jc:         -1,
	}
	if err := badJc.Validate(); err == nil {
		t.Fatalf("expected error for negative Jc")
	}

	// Invalid wireguard key
	badKeyAWG := &AmneziaWGConfig{
		PrivateKey: "invalid-key-short",
		PublicKey:  key,
		Endpoint:   "vpn.net:51820",
	}
	if err := badKeyAWG.Validate(); err == nil {
		t.Fatalf("expected error for invalid wireguard key")
	}

	// Invalid endpoint
	badEpAWG := &AmneziaWGConfig{
		PrivateKey: key,
		PublicKey:  key,
		Endpoint:   "vpn.net:999999", // Port out of range
	}
	if err := badEpAWG.Validate(); err == nil {
		t.Fatalf("expected error for out of range port in endpoint")
	}

	// Valid AWG
	goodAWG := &AmneziaWGConfig{
		Address:    "10.8.0.2/32, fd00::2/64",
		PrivateKey: key,
		PublicKey:  key,
		Endpoint:   "1.2.3.4:51820",
		AllowedIPs: "0.0.0.0/0, ::/0",
		Jc:         4,
		Jmin:       40,
		Jmax:       70,
		S1:         15,
		S2:         30,
		H1:         100,
		H2:         200,
		H3:         300,
		H4:         400,
	}
	if err := goodAWG.Validate(); err != nil {
		t.Fatalf("expected good AWG config to pass validation, got: %v", err)
	}

	// 2. OpenConnect validation
	badOCServer := &OpenConnectConfig{
		Server: "",
		Port:   443,
	}
	if err := badOCServer.Validate(); err == nil {
		t.Fatalf("expected error for empty OpenConnect server")
	}

	badOCPort := &OpenConnectConfig{
		Server: "vpn.net",
		Port:   70000,
	}
	if err := badOCPort.Validate(); err == nil {
		t.Fatalf("expected error for OpenConnect port out of range")
	}

	badOCProto := &OpenConnectConfig{
		Server:   "vpn.net",
		Port:     443,
		Protocol: "unsupported-proto",
	}
	if err := badOCProto.Validate(); err == nil {
		t.Fatalf("expected error for unsupported OpenConnect protocol")
	}

	goodOC := &OpenConnectConfig{
		Server:   "vpn.example.com",
		Port:     443,
		Username: "user",
		Password: "password",
		Protocol: "anyconnect",
	}
	if err := goodOC.Validate(); err != nil {
		t.Fatalf("expected good OpenConnect config to pass, got: %v", err)
	}

	// 3. Profile validation
	badProtoProf := Profile{
		ID:       "id1",
		Name:     "Test",
		Protocol: "wireguard", // unsupported, must be amneziawg or openconnect
	}
	if err := badProtoProf.Validate(); err == nil {
		t.Fatalf("expected error for unsupported profile protocol")
	}

	missingAWGProf := Profile{
		ID:            "id1",
		Name:          "Test",
		Protocol:      ProtocolAmneziaWG,
		AmneziaConfig: nil,
	}
	if err := missingAWGProf.Validate(); err == nil {
		t.Fatalf("expected error for missing amnezia config")
	}

	missingOCProf := Profile{
		ID:          "id1",
		Name:        "Test",
		Protocol:    ProtocolOpenConnect,
		OpenConnect: nil,
	}
	if err := missingOCProf.Validate(); err == nil {
		t.Fatalf("expected error for missing openconnect config")
	}

	// 4. Settings validation
	badThemeSettings := Settings{
		Theme: "neon-pink",
	}
	if err := badThemeSettings.Validate(); err == nil {
		t.Fatalf("expected error for invalid theme")
	}

	badLangSettings := Settings{
		Language: "fr",
	}
	if err := badLangSettings.Validate(); err == nil {
		t.Fatalf("expected error for unsupported language")
	}
}

func TestEncryptedEnvelopeJSONFormat(t *testing.T) {
	seed := []byte("envelope-test-seed")
	encryptor := NewAESGCMEncryptor(seed)

	envelope, err := encryptor.Encrypt([]byte(`{"test":"secret"}`))
	if err != nil {
		t.Fatalf("encrypt failed: %v", err)
	}

	bytes, err := json.Marshal(envelope)
	if err != nil {
		t.Fatalf("marshal envelope failed: %v", err)
	}

	var parsed StorageEnvelope
	if err := json.Unmarshal(bytes, &parsed); err != nil {
		t.Fatalf("unmarshal envelope failed: %v", err)
	}

	if parsed.Encryption != EncryptionAES256GCM || parsed.Version != 1 {
		t.Fatalf("unexpected envelope fields: %+v", parsed)
	}

	decrypted, err := encryptor.Decrypt(&parsed)
	if err != nil {
		t.Fatalf("decrypt parsed envelope failed: %v", err)
	}
	if string(decrypted) != `{"test":"secret"}` {
		t.Fatalf("unexpected decrypted data: %s", string(decrypted))
	}
}

func TestPlaintextAndLegacyConfigMigration(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "bobr_migration_test_*")
	if err != nil {
		t.Fatalf("failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	// 1. Plaintext StoreState migration
	plainPath := filepath.Join(tmpDir, "plain_settings.json")
	plainData := []byte(`{
		"settings": {
			"active_profile_id": "prof-plain-1",
			"subscription_url": "https://persona.netphoenix.ru/sub/plain",
			"theme": "dark",
			"language": "ru"
		},
		"profiles": [
			{
				"id": "prof-plain-1",
				"name": "Plain Amsterdam",
				"protocol": "amneziawg",
				"server": "1.2.3.4",
				"port": 443,
				"raw_config": "[Interface]\nAddress = 10.0.0.2/32\n",
				"amnezia_config": {
					"config_content": "[Interface]\nAddress = 10.0.0.2/32\n"
				}
			}
		]
	}`)
	if err := os.WriteFile(plainPath, plainData, 0600); err != nil {
		t.Fatalf("failed writing plain file: %v", err)
	}

	store1, err := NewStore(plainPath)
	if err != nil {
		t.Fatalf("failed to open store with plaintext data: %v", err)
	}
	profs1, _ := store1.ListProfiles()
	if len(profs1) != 1 || profs1[0].Name != "Plain Amsterdam" {
		t.Fatalf("failed loading profile from plain data: %+v", profs1)
	}

	// Trigger save and ensure it re-writes as encrypted envelope
	if err := store1.SaveProfile(profs1[0]); err != nil {
		t.Fatalf("failed save: %v", err)
	}
	fileBytes, _ := os.ReadFile(plainPath)
	var envelope StorageEnvelope
	if err := json.Unmarshal(fileBytes, &envelope); err != nil || envelope.Encryption != EncryptionAES256GCM {
		t.Fatalf("expected file to be re-saved as encrypted envelope, got: %s", string(fileBytes))
	}

	// 2. Legacy Python settings.json migration
	legacyPath := filepath.Join(tmpDir, "python_settings.json")
	legacyData := []byte(`{
		"active_profile_id": "legacy-py-1",
		"subscription_url": "https://persona.netphoenix.ru/sub/python-token",
		"kill_switch": true,
		"profiles": [
			{
				"id": "legacy-py-1",
				"name": "Python AWG",
				"proto": "amnezia",
				"server": "5.6.7.8",
				"port": 51820,
				"config_content": "[Interface]\nPrivateKey = testkey\n"
			},
			{
				"id": "legacy-py-2",
				"name": "Python OC",
				"proto": "openconnect",
				"server": "vpn.example.com",
				"port": 443,
				"username": "pyuser",
				"password": "pypassword",
				"camouflage": "kurwa"
			}
		]
	}`)
	if err := os.WriteFile(legacyPath, legacyData, 0600); err != nil {
		t.Fatalf("failed writing legacy python file: %v", err)
	}

	store2, err := NewStore(legacyPath)
	if err != nil {
		t.Fatalf("failed to open store with legacy python data: %v", err)
	}
	settings2, _ := store2.GetSettings()
	if settings2.ActiveProfileID != "legacy-py-1" || settings2.SubscriptionURL != "https://persona.netphoenix.ru/sub/python-token" {
		t.Fatalf("unexpected migrated settings: %+v", settings2)
	}
	profs2, _ := store2.ListProfiles()
	if len(profs2) != 2 {
		t.Fatalf("expected 2 migrated profiles, got %d", len(profs2))
	}
	if profs2[0].Protocol != ProtocolAmneziaWG || profs2[1].Protocol != ProtocolOpenConnect {
		t.Fatalf("unexpected migrated protocols: %s, %s", profs2[0].Protocol, profs2[1].Protocol)
	}
	if profs2[1].OpenConnect == nil || profs2[1].OpenConnect.Camouflage != "kurwa" {
		t.Fatalf("unexpected openconnect camouflage: %+v", profs2[1].OpenConnect)
	}
}

func TestSettings_SilentTray(t *testing.T) {
	defaults := DefaultSettings()
	if defaults.SilentTray != false {
		t.Fatalf("expected DefaultSettings().SilentTray to be false, got true")
	}

	rawJSON := `{"close_action":"tray","silent_tray":true}`
	var s Settings
	if err := json.Unmarshal([]byte(rawJSON), &s); err != nil {
		t.Fatalf("json unmarshal failed: %v", err)
	}
	if !s.SilentTray {
		t.Fatalf("expected s.SilentTray to be true, got false")
	}

	data, err := json.Marshal(s)
	if err != nil {
		t.Fatalf("json marshal failed: %v", err)
	}
	if string(data) == "" {
		t.Fatalf("expected non-empty json")
	}
}
