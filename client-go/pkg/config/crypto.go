package config

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"errors"
	"fmt"
	"hash"
	"io"
	"os"
	"runtime"
	"strings"
)

// Encryption algorithms supported.
const (
	EncryptionAES256GCM = "aes-256-gcm"
	EncryptionDPAPI     = "dpapi"
	EncryptionNone      = "none"
)

var (
	ErrDecryptionFailed      = errors.New("decryption failed: authentication tag mismatch or corrupted data")
	ErrUnsupportedEncryption = errors.New("unsupported encryption algorithm")
	ErrNilEnvelope           = errors.New("storage envelope cannot be nil")
	ErrEmptyData             = errors.New("storage data cannot be empty")
)

// StorageEnvelope encapsulates encrypted data and encryption metadata for safe persistent storage.
type StorageEnvelope struct {
	Version    int    `json:"version"`
	Encryption string `json:"encryption"` // "aes-256-gcm", "dpapi", "none"
	Salt       string `json:"salt,omitempty"`
	Nonce      string `json:"nonce,omitempty"`
	Data       string `json:"data"` // base64 encoded payload
}

// Encryptor defines the contract for encrypting and decrypting configuration payloads.
type Encryptor interface {
	Encrypt(plaintext []byte) (*StorageEnvelope, error)
	Decrypt(envelope *StorageEnvelope) ([]byte, error)
}

// AESGCMEncryptor implements AES-256-GCM authenticated encryption using PBKDF2 key derivation.
type AESGCMEncryptor struct {
	secretSeed []byte
	iterations int
}

// NewAESGCMEncryptor creates a new AES-256-GCM encryptor.
// If secretSeed is nil or empty, a hardware-derived machine key is automatically used.
func NewAESGCMEncryptor(secretSeed []byte) *AESGCMEncryptor {
	if len(secretSeed) == 0 {
		secretSeed = GetHardwareDerivedKey()
	}
	seedCopy := make([]byte, len(secretSeed))
	copy(seedCopy, secretSeed)
	return &AESGCMEncryptor{
		secretSeed: seedCopy,
		iterations: 10000,
	}
}

// Encrypt encrypts plaintext using AES-256-GCM with a randomly generated 16-byte salt and 12-byte nonce.
func (e *AESGCMEncryptor) Encrypt(plaintext []byte) (*StorageEnvelope, error) {
	salt := make([]byte, 16)
	if _, err := io.ReadFull(rand.Reader, salt); err != nil {
		return nil, fmt.Errorf("failed to generate random salt: %w", err)
	}

	key := pbkdf2(e.secretSeed, salt, e.iterations, 32, sha256.New)

	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, fmt.Errorf("failed to create AES cipher: %w", err)
	}

	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, fmt.Errorf("failed to create GCM mode: %w", err)
	}

	nonce := make([]byte, gcm.NonceSize())
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		return nil, fmt.Errorf("failed to generate random nonce: %w", err)
	}

	ciphertext := gcm.Seal(nil, nonce, plaintext, nil)

	return &StorageEnvelope{
		Version:    1,
		Encryption: EncryptionAES256GCM,
		Salt:       base64.StdEncoding.EncodeToString(salt),
		Nonce:      base64.StdEncoding.EncodeToString(nonce),
		Data:       base64.StdEncoding.EncodeToString(ciphertext),
	}, nil
}

// Decrypt decrypts the ciphertext in the envelope and verifies integrity.
func (e *AESGCMEncryptor) Decrypt(envelope *StorageEnvelope) ([]byte, error) {
	if envelope == nil {
		return nil, ErrNilEnvelope
	}
	if envelope.Encryption != EncryptionAES256GCM {
		return nil, fmt.Errorf("%w: %s", ErrUnsupportedEncryption, envelope.Encryption)
	}

	salt, err := base64.StdEncoding.DecodeString(envelope.Salt)
	if err != nil || len(salt) < 16 {
		return nil, fmt.Errorf("%w: invalid salt", ErrDecryptionFailed)
	}

	nonce, err := base64.StdEncoding.DecodeString(envelope.Nonce)
	if err != nil {
		return nil, fmt.Errorf("%w: invalid nonce", ErrDecryptionFailed)
	}

	ciphertext, err := base64.StdEncoding.DecodeString(envelope.Data)
	if err != nil {
		return nil, fmt.Errorf("%w: invalid ciphertext base64", ErrDecryptionFailed)
	}

	key := pbkdf2(e.secretSeed, salt, e.iterations, 32, sha256.New)

	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, fmt.Errorf("failed to create AES cipher: %w", err)
	}

	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, fmt.Errorf("failed to create GCM mode: %w", err)
	}

	if len(nonce) != gcm.NonceSize() {
		return nil, fmt.Errorf("%w: invalid nonce length", ErrDecryptionFailed)
	}

	plaintext, err := gcm.Open(nil, nonce, ciphertext, nil)
	if err != nil {
		return nil, ErrDecryptionFailed
	}

	return plaintext, nil
}

// DPAPIEncryptor implements Windows DPAPI encryption.
type DPAPIEncryptor struct{}

// NewDPAPIEncryptor returns a new Windows DPAPI encryptor.
func NewDPAPIEncryptor() *DPAPIEncryptor {
	return &DPAPIEncryptor{}
}

// Encrypt encrypts data using Windows DPAPI CryptProtectData.
func (d *DPAPIEncryptor) Encrypt(plaintext []byte) (*StorageEnvelope, error) {
	blob, err := dpapiProtect(plaintext)
	if err != nil {
		return nil, fmt.Errorf("dpapi protect failed: %w", err)
	}
	return &StorageEnvelope{
		Version:    1,
		Encryption: EncryptionDPAPI,
		Data:       base64.StdEncoding.EncodeToString(blob),
	}, nil
}

// Decrypt decrypts data using Windows DPAPI CryptUnprotectData.
func (d *DPAPIEncryptor) Decrypt(envelope *StorageEnvelope) ([]byte, error) {
	if envelope == nil {
		return nil, ErrNilEnvelope
	}
	if envelope.Encryption != EncryptionDPAPI {
		return nil, fmt.Errorf("%w: %s", ErrUnsupportedEncryption, envelope.Encryption)
	}
	blob, err := base64.StdEncoding.DecodeString(envelope.Data)
	if err != nil {
		return nil, fmt.Errorf("%w: invalid base64", ErrDecryptionFailed)
	}
	plaintext, err := dpapiUnprotect(blob)
	if err != nil {
		return nil, fmt.Errorf("%w: dpapi unprotect: %v", ErrDecryptionFailed, err)
	}
	return plaintext, nil
}

// CompositeEncryptor handles both AES-256-GCM and DPAPI envelopes seamlessly,
// using a configured primary encryptor for encryption and falling back appropriately.
type CompositeEncryptor struct {
	primary   Encryptor
	aesGCM    *AESGCMEncryptor
	dpapi     *DPAPIEncryptor
}

// NewCompositeEncryptor creates an encryptor that can decrypt any supported envelope format.
// primary is used for new encryptions (default is AES-256-GCM).
func NewCompositeEncryptor(primary Encryptor, secretSeed []byte) *CompositeEncryptor {
	aesEnc := NewAESGCMEncryptor(secretSeed)
	dpapiEnc := NewDPAPIEncryptor()
	if primary == nil {
		primary = aesEnc
	}
	return &CompositeEncryptor{
		primary: primary,
		aesGCM:  aesEnc,
		dpapi:   dpapiEnc,
	}
}

func (c *CompositeEncryptor) Encrypt(plaintext []byte) (*StorageEnvelope, error) {
	return c.primary.Encrypt(plaintext)
}

func (c *CompositeEncryptor) Decrypt(envelope *StorageEnvelope) ([]byte, error) {
	if envelope == nil {
		return nil, ErrNilEnvelope
	}
	switch envelope.Encryption {
	case EncryptionAES256GCM:
		return c.aesGCM.Decrypt(envelope)
	case EncryptionDPAPI:
		return c.dpapi.Decrypt(envelope)
	case EncryptionNone:
		return base64.StdEncoding.DecodeString(envelope.Data)
	default:
		return nil, fmt.Errorf("%w: %s", ErrUnsupportedEncryption, envelope.Encryption)
	}
}

// GetHardwareDerivedKey generates a stable machine-bound seed for local key derivation.
func GetHardwareDerivedKey() []byte {
	var parts []string

	// Hostname
	if host, err := os.Hostname(); err == nil && host != "" {
		parts = append(parts, host)
	}

	// User info
	for _, envVar := range []string{"COMPUTERNAME", "USERNAME", "USER", "HOSTNAME"} {
		if val := os.Getenv(envVar); val != "" {
			parts = append(parts, val)
		}
	}

	// OS and architecture
	parts = append(parts, runtime.GOOS, runtime.GOARCH)

	// Linux machine-id if available
	for _, idFile := range []string{"/etc/machine-id", "/var/lib/dbus/machine-id"} {
		if data, err := os.ReadFile(idFile); err == nil && len(data) > 0 {
			parts = append(parts, strings.TrimSpace(string(data)))
			break
		}
	}

	// Application-specific fixed salt
	parts = append(parts, "BobrDobr_Salt_SecKey_2026")

	seedStr := strings.Join(parts, "|")
	h := sha256.Sum256([]byte(seedStr))
	return h[:]
}

// RFC 2898 standard PBKDF2 implementation using standard library crypto/hmac and hash.
func pbkdf2(password, salt []byte, iter, keyLen int, h func() hash.Hash) []byte {
	prf := hmac.New(h, password)
	hashLen := prf.Size()
	numBlocks := (keyLen + hashLen - 1) / hashLen
	var buf [4]byte
	dk := make([]byte, 0, numBlocks*hashLen)
	u := make([]byte, hashLen)
	t := make([]byte, hashLen)

	for block := 1; block <= numBlocks; block++ {
		prf.Reset()
		prf.Write(salt)
		buf[0] = byte(block >> 24)
		buf[1] = byte(block >> 16)
		buf[2] = byte(block >> 8)
		buf[3] = byte(block)
		prf.Write(buf[:4])
		u = prf.Sum(u[:0])
		copy(t, u)

		for i := 2; i <= iter; i++ {
			prf.Reset()
			prf.Write(u)
			u = prf.Sum(u[:0])
			for k := 0; k < hashLen; k++ {
				t[k] ^= u[k]
			}
		}
		dk = append(dk, t...)
	}
	return dk[:keyLen]
}
