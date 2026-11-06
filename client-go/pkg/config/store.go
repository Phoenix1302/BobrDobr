package config

import (
	"crypto/rand"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"runtime"
	"sync"
	"time"
)

var (
	ErrProfileNotFound = errors.New("profile not found")
	ErrStoreCorrupted  = errors.New("store corrupted and no valid backup available")
)

// StoreState represents the serialized schema saved inside the encrypted vault.
type StoreState struct {
	Settings Settings  `json:"settings"`
	Profiles []Profile `json:"profiles"`
}

// StoreOption defines functional configuration options for Store.
type StoreOption func(*Store)

// WithEncryptor configures a custom encryptor for the store.
func WithEncryptor(e Encryptor) StoreOption {
	return func(s *Store) {
		s.encryptor = e
	}
}

// WithBackupPath configures a custom backup file path.
func WithBackupPath(path string) StoreOption {
	return func(s *Store) {
		s.bakPath = path
	}
}

// Store manages encrypted persistent storage of VPN profiles and user preferences.
type Store struct {
	filePath  string
	bakPath   string
	tmpPath   string
	mu        sync.RWMutex
	encryptor Encryptor
	state     StoreState
}

// NewStore creates a new Store instance and loads existing settings or initializes defaults.
func NewStore(filePath string, opts ...StoreOption) (*Store, error) {
	if filePath == "" {
		return nil, errors.New("store file path cannot be empty")
	}

	cleanPath := filepath.Clean(filePath)
	store := &Store{
		filePath: cleanPath,
		bakPath:  cleanPath + ".bak",
		tmpPath:  cleanPath + ".tmp",
		state: StoreState{
			Settings: DefaultSettings(),
			Profiles: make([]Profile, 0),
		},
	}

	// Default encryptor: Composite (handles AES-GCM and DPAPI)
	store.encryptor = NewCompositeEncryptor(NewAESGCMEncryptor(nil), nil)

	for _, opt := range opts {
		opt(store)
	}

	// Ensure directory exists
	dir := filepath.Dir(cleanPath)
	if err := os.MkdirAll(dir, 0700); err != nil {
		return nil, fmt.Errorf("failed to create config directory: %w", err)
	}

	// Load existing file or initialize
	if err := store.loadWithFallback(); err != nil {
		return nil, err
	}

	return store, nil
}

// GetSettings returns a copy of current user preferences.
func (s *Store) GetSettings() (Settings, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.state.Settings, nil
}

// SaveSettings updates and atomically persists settings to disk.
func (s *Store) SaveSettings(settings Settings) error {
	if err := settings.Validate(); err != nil {
		return fmt.Errorf("invalid settings: %w", err)
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	s.state.Settings = settings
	return s.persistLocked()
}

// ListProfiles returns a copy of all configured profiles.
func (s *Store) ListProfiles() ([]Profile, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	result := make([]Profile, len(s.state.Profiles))
	copy(result, s.state.Profiles)
	return result, nil
}

// GetProfile retrieves a profile by ID.
func (s *Store) GetProfile(id string) (Profile, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	for _, p := range s.state.Profiles {
		if p.ID == id {
			return p, nil
		}
	}
	return Profile{}, ErrProfileNotFound
}

// SaveProfile creates or updates a profile and atomically persists to disk.
func (s *Store) SaveProfile(profile Profile) error {
	if profile.ID == "" {
		profile.ID = generateUUID()
	}
	if profile.CreatedAt.IsZero() {
		profile.CreatedAt = time.Now().UTC()
	}

	if err := profile.Validate(); err != nil {
		return fmt.Errorf("invalid profile: %w", err)
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	found := false
	for i, p := range s.state.Profiles {
		if p.ID == profile.ID {
			s.state.Profiles[i] = profile
			found = true
			break
		}
	}
	if !found {
		s.state.Profiles = append(s.state.Profiles, profile)
	}

	return s.persistLocked()
}

// DeleteProfile removes a profile by ID and atomically persists to disk.
func (s *Store) DeleteProfile(id string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	foundIdx := -1
	for i, p := range s.state.Profiles {
		if p.ID == id {
			foundIdx = i
			break
		}
	}

	if foundIdx == -1 {
		return ErrProfileNotFound
	}

	s.state.Profiles = append(s.state.Profiles[:foundIdx], s.state.Profiles[foundIdx+1:]...)

	if s.state.Settings.ActiveProfileID == id {
		s.state.Settings.ActiveProfileID = ""
	}

	return s.persistLocked()
}

// loadWithFallback attempts to load from the main file, falling back to .bak if corruption occurs.
func (s *Store) loadWithFallback() error {
	s.mu.Lock()
	defer s.mu.Unlock()

	mainExists := fileExists(s.filePath)
	bakExists := fileExists(s.bakPath)

	if !mainExists && !bakExists {
		// New store, no file yet
		return nil
	}

	var mainErr error
	if mainExists {
		state, err := s.readAndDecryptFile(s.filePath)
		if err == nil {
			s.state = *state
			return nil
		}
		mainErr = err
	}

	// Main file is missing or corrupted: attempt fallback to .bak
	if bakExists {
		state, err := s.readAndDecryptFile(s.bakPath)
		if err == nil {
			s.state = *state
			// Restore main file from healthy backup
			_ = s.persistLocked()
			return nil
		}
		return fmt.Errorf("%w: main error (%v), backup error (%v)", ErrStoreCorrupted, mainErr, err)
	}

	return fmt.Errorf("%w: %v", ErrStoreCorrupted, mainErr)
}

// readAndDecryptFile reads, parses envelope, decrypts and deserializes StoreState.
// If the file is unencrypted or in legacy format, it transparently imports it so that
// subsequent writes will securely encrypt it at rest.
func (s *Store) readAndDecryptFile(path string) (*StoreState, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	if len(data) == 0 {
		return nil, errors.New("empty file content")
	}

	var envelope StorageEnvelope
	unmarshalErr := json.Unmarshal(data, &envelope)

	// Case 1: Valid encrypted envelope
	if unmarshalErr == nil && envelope.Data != "" && (envelope.Encryption == EncryptionAES256GCM || envelope.Encryption == EncryptionDPAPI) {
		plaintext, err := s.encryptor.Decrypt(&envelope)
		if err != nil {
			return nil, fmt.Errorf("decrypt failed: %w", err)
		}

		var state StoreState
		if err := json.Unmarshal(plaintext, &state); err != nil {
			return nil, fmt.Errorf("payload unmarshal failed: %w", err)
		}

		return &state, nil
	}

	// Case 2 & 3: Plaintext inspection
	var rawCheck map[string]json.RawMessage
	if err := json.Unmarshal(data, &rawCheck); err == nil {
		// Case 2: Native plaintext StoreState JSON format (has explicit "settings" object)
		if _, hasSettings := rawCheck["settings"]; hasSettings {
			var plainState StoreState
			if err := json.Unmarshal(data, &plainState); err == nil {
				return &plainState, nil
			}
		}

		// Case 3: Legacy Python client settings.json format (top-level properties)
		var legacyMap map[string]interface{}
		if err := json.Unmarshal(data, &legacyMap); err == nil {
			if migrated := migrateLegacyConfig(legacyMap); migrated != nil {
				return migrated, nil
			}
		}
	}

	if unmarshalErr != nil {
		return nil, fmt.Errorf("envelope unmarshal failed: %w", unmarshalErr)
	}
	return nil, errors.New("invalid or empty storage envelope")
}

// migrateLegacyConfig maps legacy Python configuration keys into StoreState.
func migrateLegacyConfig(raw map[string]interface{}) *StoreState {
	state := &StoreState{
		Settings: DefaultSettings(),
		Profiles: make([]Profile, 0),
	}

	if v, ok := raw["active_profile_id"].(string); ok {
		state.Settings.ActiveProfileID = v
	}
	if v, ok := raw["subscription_url"].(string); ok {
		state.Settings.SubscriptionURL = v
	}
	if v, ok := raw["subscription_token"].(string); ok {
		state.Settings.SubscriptionToken = v
	}
	if v, ok := raw["kill_switch"].(bool); ok {
		state.Settings.KillSwitch = v
	}
	if v, ok := raw["dns_leak_protection"].(bool); ok {
		state.Settings.DNSLeakProtection = v
	}

	rawProfiles, ok := raw["profiles"].([]interface{})
	if !ok || len(rawProfiles) == 0 {
		return state
	}

	for _, item := range rawProfiles {
		pMap, ok := item.(map[string]interface{})
		if !ok {
			continue
		}

		id, _ := pMap["id"].(string)
		name, _ := pMap["name"].(string)
		proto, _ := pMap["proto"].(string)
		server, _ := pMap["server"].(string)
		port := 443
		if pVal, ok := pMap["port"].(float64); ok {
			port = int(pVal)
		}

		if id == "" {
			id = fmt.Sprintf("prof-%d", time.Now().UnixNano())
		}
		if name == "" {
			name = "Imported Profile"
		}

		p := Profile{
			ID:        id,
			Name:      name,
			Server:    server,
			Port:      port,
			CreatedAt: time.Now().UTC(),
		}

		isSub, _ := pMap["is_subscription"].(bool)
		p.IsSubscription = isSub

		if proto == "openconnect" {
			p.Protocol = ProtocolOpenConnect
			user, _ := pMap["username"].(string)
			pass, _ := pMap["password"].(string)
			camo, _ := pMap["camouflage"].(string)
			p.OpenConnect = &OpenConnectConfig{
				Server:     server,
				Port:       port,
				Username:   user,
				Password:   pass,
				Camouflage: camo,
				Protocol:   "anyconnect",
			}
		} else {
			p.Protocol = ProtocolAmneziaWG
			confContent, _ := pMap["config_content"].(string)
			p.RawConfig = confContent
			p.AmneziaConfig = &AmneziaWGConfig{
				ConfigContent: confContent,
			}
		}

		state.Profiles = append(state.Profiles, p)
	}

	return state
}

// persistLocked atomically writes state to disk with .bak fallback.
// Caller MUST hold s.mu Lock.
func (s *Store) persistLocked() error {
	raw, err := json.Marshal(s.state)
	if err != nil {
		return fmt.Errorf("failed to marshal store state: %w", err)
	}

	envelope, err := s.encryptor.Encrypt(raw)
	if err != nil {
		return fmt.Errorf("failed to encrypt store state: %w", err)
	}

	envelopeBytes, err := json.MarshalIndent(envelope, "", "  ")
	if err != nil {
		return fmt.Errorf("failed to marshal storage envelope: %w", err)
	}

	// 1. If destination file exists and is valid, backup to .bak
	if fileExists(s.filePath) {
		currentBytes, err := os.ReadFile(s.filePath)
		if err == nil && len(currentBytes) > 0 {
			_ = safeWriteFile(s.bakPath, currentBytes)
		}
	}

	// 2. Atomic write: write to .tmp, flush, sync, rename
	if err := safeWriteFile(s.tmpPath, envelopeBytes); err != nil {
		return fmt.Errorf("failed to write tmp file: %w", err)
	}

	// 3. Atomic rename tmp -> destination
	if err := atomicRename(s.tmpPath, s.filePath); err != nil {
		_ = os.Remove(s.tmpPath)
		return fmt.Errorf("failed to atomically rename config file: %w", err)
	}

	return nil
}

// safeWriteFile writes data to path with flush/sync to ensure durability.
func safeWriteFile(path string, data []byte) error {
	f, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0600)
	if err != nil {
		return err
	}
	defer f.Close()

	if _, err := f.Write(data); err != nil {
		return err
	}

	return f.Sync()
}

// atomicRename handles atomic replace across operating systems.
func atomicRename(src, dst string) error {
	err := os.Rename(src, dst)
	if err == nil {
		return nil
	}
	if runtime.GOOS == "windows" {
		// On Windows, if destination exists, remove first then rename
		_ = os.Remove(dst)
		return os.Rename(src, dst)
	}
	return err
}

func fileExists(path string) bool {
	info, err := os.Stat(path)
	return err == nil && !info.IsDir()
}

// generateUUID generates RFC 4122 v4 UUID.
func generateUUID() string {
	var b [16]byte
	_, _ = io.ReadFull(rand.Reader, b[:])
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	return fmt.Sprintf("%08x-%04x-%04x-%04x-%012x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}
