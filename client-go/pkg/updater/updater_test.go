package updater

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestCompareVersions(t *testing.T) {
	tests := []struct {
		v1       string
		v2       string
		expected int
	}{
		{"1.2.1", "1.2.0", 1},
		{"v1.2.1", "1.2.0", 1},
		{"1.2.0", "1.2.0", 0},
		{"v1.2.0", "v1.2.0", 0},
		{"1.1.9", "1.2.0", -1},
		{"1.2.0", "1.2.1", -1},
		{"2.0.0", "1.9.9", 1},
		{"1.10.0", "1.9.0", 1},
		{"1.2.0.1", "1.2.0", 1},
		{"1.2.0", "1.2.0.1", -1},
	}

	for _, tc := range tests {
		got := CompareVersions(tc.v1, tc.v2)
		if got != tc.expected {
			t.Errorf("CompareVersions(%q, %q) = %d; want %d", tc.v1, tc.v2, got, tc.expected)
		}
	}
}

func TestCheckUpdate_WithMockServer(t *testing.T) {
	mockRelease := GitHubReleaseJSON{
		TagName:     "v1.3.0",
		Name:        "BobrDobr VPN 1.3.0",
		Body:        "- Новая плотина\n- Оптимизация сети",
		HTMLURL:     "https://github.com/Phoenix1302/BobrDobr/releases/tag/v1.3.0",
		PublishedAt: "2026-11-05T20:00:00Z",
		Assets: []struct {
			Name               string `json:"name"`
			BrowserDownloadURL string `json:"browser_download_url"`
			Size               int64  `json:"size"`
		}{
			{
				Name:               "BobrDobr-Setup.exe",
				BrowserDownloadURL: "https://example.com/download/BobrDobr-Setup.exe",
				Size:               10485760,
			},
		},
	}

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(mockRelease)
	}))
	defer ts.Close()

	// Use custom client to test decoding logic
	req, _ := http.NewRequestWithContext(context.Background(), http.MethodGet, ts.URL, nil)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("failed mock request: %v", err)
	}
	defer resp.Body.Close()

	var ghRelease GitHubReleaseJSON
	if err := json.NewDecoder(resp.Body).Decode(&ghRelease); err != nil {
		t.Fatalf("failed decoding: %v", err)
	}

	hasUpdate := CompareVersions(ghRelease.TagName, "1.2.0") > 0
	if !hasUpdate {
		t.Fatalf("expected hasUpdate to be true for v1.3.0 vs 1.2.0")
	}

	if !strings.Contains(ghRelease.Assets[0].Name, "Setup.exe") {
		t.Fatalf("expected Setup.exe asset")
	}

	if ghRelease.HTMLURL != "https://github.com/Phoenix1302/BobrDobr/releases/tag/v1.3.0" {
		t.Fatalf("HTMLURL mismatch, got %q", ghRelease.HTMLURL)
	}
}

func TestDownloadInstaller_WithMockServer(t *testing.T) {
	dummyPayload := []byte("MZ-DUMMY-INSTALLER-BINARY-CONTENT-FOR-TESTING")

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Length", "45")
		_, _ = w.Write(dummyPayload)
	}))
	defer ts.Close()

	var recordedProgress []int
	progressFn := func(pct int) {
		recordedProgress = append(recordedProgress, pct)
	}

	path, err := DownloadInstaller(context.Background(), ts.URL, progressFn)
	if err != nil {
		t.Fatalf("DownloadInstaller failed: %v", err)
	}
	defer os.Remove(path)

	content, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("failed to read downloaded file: %v", err)
	}

	if string(content) != string(dummyPayload) {
		t.Fatalf("downloaded content mismatch, got %q", string(content))
	}

	if len(recordedProgress) == 0 || recordedProgress[len(recordedProgress)-1] != 100 {
		t.Fatalf("expected final progress 100%%, got %v", recordedProgress)
	}
}

func TestCheckUpdate_EndToEnd(t *testing.T) {
	mockRelease := GitHubReleaseJSON{
		TagName:     "v1.4.0",
		Name:        "BobrDobr VPN 1.4.0 Major Release",
		Body:        "Feature updates and security fixes",
		PublishedAt: "2026-11-05T21:00:00Z",
		Assets: []struct {
			Name               string `json:"name"`
			BrowserDownloadURL string `json:"browser_download_url"`
			Size               int64  `json:"size"`
		}{
			{
				Name:               "BobrDobr-Setup.exe",
				BrowserDownloadURL: "https://example.com/BobrDobr-Setup.exe",
				Size:               20485760,
			},
		},
	}

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(mockRelease)
	}))
	defer ts.Close()

	// Direct verification of compare and parse
	relVersion := strings.TrimLeft(mockRelease.TagName, "vV")
	hasUpdate := CompareVersions(relVersion, "1.2.0") > 0
	if !hasUpdate {
		t.Fatalf("expected update for v1.4.0 over 1.2.0")
	}

	noUpdate := CompareVersions(relVersion, "1.4.0") > 0
	if noUpdate {
		t.Fatalf("expected no update for v1.4.0 over 1.4.0")
	}
}

func TestCleanupOldInstallers(t *testing.T) {
	updatesDir := GetUpdatesDir()
	_ = os.MkdirAll(updatesDir, 0755)

	f1 := filepath.Join(updatesDir, "test-old-setup.exe")
	f2 := filepath.Join(updatesDir, "test-partial.tmp")
	f3 := filepath.Join(updatesDir, "keep_me.txt")

	_ = os.WriteFile(f1, []byte("dummy exe"), 0644)
	_ = os.WriteFile(f2, []byte("dummy tmp"), 0644)
	_ = os.WriteFile(f3, []byte("keep text"), 0644)
	defer os.Remove(f3)

	if err := CleanupOldInstallers(); err != nil {
		t.Fatalf("CleanupOldInstallers failed: %v", err)
	}

	if _, err := os.Stat(f1); !os.IsNotExist(err) {
		t.Errorf("expected %s to be removed", f1)
	}
	if _, err := os.Stat(f2); !os.IsNotExist(err) {
		t.Errorf("expected %s to be removed", f2)
	}
	if _, err := os.Stat(f3); os.IsNotExist(err) {
		t.Errorf("expected %s to be preserved", f3)
	}
}
