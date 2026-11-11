package updater

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"
)

var (
	ErrNoReleaseFound    = errors.New("no releases found on update server")
	ErrNoInstallerAsset  = errors.New("release does not contain a setup installer asset")
	ErrDownloadCancelled = errors.New("update download was cancelled")
)

const (
	DefaultGitHubRepo = "Phoenix1302/BobrDobr"
	UserAgent         = "BobrDobr-Updater/1.3.0"
)

// ReleaseInfo holds metadata for a published application release.
type ReleaseInfo struct {
	Version     string    `json:"version"`
	TagName     string    `json:"tag_name"`
	Title       string    `json:"title"`
	Description string    `json:"description"`
	DownloadURL string    `json:"download_url"`
	HTMLURL     string    `json:"html_url"`
	AssetSize   int64     `json:"asset_size"`
	PublishedAt time.Time `json:"published_at"`
}

// GitHubReleaseJSON represents the payload from GitHub Releases API.
type GitHubReleaseJSON struct {
	TagName     string `json:"tag_name"`
	Name        string `json:"name"`
	Body        string `json:"body"`
	HTMLURL     string `json:"html_url"`
	PublishedAt string `json:"published_at"`
	Assets      []struct {
		Name               string `json:"name"`
		BrowserDownloadURL string `json:"browser_download_url"`
		Size               int64  `json:"size"`
	} `json:"assets"`
}

// CompareVersions returns:
//  1 if v1 > v2
// -1 if v1 < v2
//  0 if v1 == v2
func CompareVersions(v1, v2 string) int {
	cleanV1 := strings.TrimLeft(strings.TrimSpace(v1), "vV")
	cleanV2 := strings.TrimLeft(strings.TrimSpace(v2), "vV")

	parts1 := splitVersion(cleanV1)
	parts2 := splitVersion(cleanV2)

	maxLen := len(parts1)
	if len(parts2) > maxLen {
		maxLen = len(parts2)
	}

	for i := 0; i < maxLen; i++ {
		num1 := 0
		if i < len(parts1) {
			num1 = parts1[i]
		}
		num2 := 0
		if i < len(parts2) {
			num2 = parts2[i]
		}

		if num1 > num2 {
			return 1
		}
		if num1 < num2 {
			return -1
		}
	}

	return 0
}

func splitVersion(v string) []int {
	re := regexp.MustCompile(`\d+`)
	matches := re.FindAllString(v, -1)
	nums := make([]int, 0, len(matches))
	for _, m := range matches {
		if n, err := strconv.Atoi(m); err == nil {
			nums = append(nums, n)
		}
	}
	return nums
}

// CheckUpdate checks GitHub Releases API for a newer version of BobrDobr VPN.
func CheckUpdate(ctx context.Context, repo, currentVersion string) (*ReleaseInfo, bool, error) {
	if repo == "" {
		repo = DefaultGitHubRepo
	}

	apiURL := fmt.Sprintf("https://api.github.com/repos/%s/releases/latest", repo)

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, apiURL, nil)
	if err != nil {
		return nil, false, fmt.Errorf("failed to create update request: %w", err)
	}

	req.Header.Set("User-Agent", UserAgent)
	req.Header.Set("Accept", "application/vnd.github.v3+json")

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return nil, false, fmt.Errorf("failed to query update server: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotFound {
		return nil, false, ErrNoReleaseFound
	}
	if resp.StatusCode != http.StatusOK {
		return nil, false, fmt.Errorf("update server returned HTTP %d", resp.StatusCode)
	}

	var ghRelease GitHubReleaseJSON
	if err := json.NewDecoder(resp.Body).Decode(&ghRelease); err != nil {
		return nil, false, fmt.Errorf("failed to parse release metadata: %w", err)
	}

	var installerURL string
	var assetSize int64

	// Search for BobrDobr-Setup.exe or any .exe asset
	for _, asset := range ghRelease.Assets {
		lower := strings.ToLower(asset.Name)
		if strings.Contains(lower, "setup") && strings.HasSuffix(lower, ".exe") {
			installerURL = asset.BrowserDownloadURL
			assetSize = asset.Size
			break
		}
	}
	if installerURL == "" {
		for _, asset := range ghRelease.Assets {
			if strings.HasSuffix(strings.ToLower(asset.Name), ".exe") {
				installerURL = asset.BrowserDownloadURL
				assetSize = asset.Size
				break
			}
		}
	}

	relVersion := strings.TrimLeft(ghRelease.TagName, "vV")
	pubTime, _ := time.Parse(time.RFC3339, ghRelease.PublishedAt)

	htmlURL := ghRelease.HTMLURL
	if htmlURL == "" {
		htmlURL = fmt.Sprintf("https://github.com/%s/releases/tag/%s", repo, ghRelease.TagName)
	}

	info := &ReleaseInfo{
		Version:     relVersion,
		TagName:     ghRelease.TagName,
		Title:       ghRelease.Name,
		Description: ghRelease.Body,
		DownloadURL: installerURL,
		HTMLURL:     htmlURL,
		AssetSize:   assetSize,
		PublishedAt: pubTime,
	}

	hasUpdate := CompareVersions(relVersion, currentVersion) > 0
	return info, hasUpdate, nil
}

// GetUpdatesDir returns the dedicated updates folder in LocalAppData (or fallback AppData / Temp).
func GetUpdatesDir() string {
	localAppData := os.Getenv("LOCALAPPDATA")
	if localAppData == "" {
		localAppData = os.Getenv("APPDATA")
	}
	if localAppData == "" {
		home, _ := os.UserHomeDir()
		if home != "" {
			localAppData = filepath.Join(home, "AppData", "Local")
		} else {
			localAppData = os.TempDir()
		}
	}
	return filepath.Join(localAppData, "BobrDobr", "updates")
}

// CleanupOldInstallers removes all downloaded installers (.exe) and temporary download files (.tmp)
// from the updates directory and legacy temporary update locations.
func CleanupOldInstallers() error {
	dirs := []string{
		GetUpdatesDir(),
		filepath.Join(os.TempDir(), "BobrDobr-Update"),
	}

	var errs []string
	for _, dir := range dirs {
		entries, err := os.ReadDir(dir)
		if err != nil {
			if os.IsNotExist(err) {
				continue
			}
			errs = append(errs, fmt.Sprintf("cannot read dir %s: %v", dir, err))
			continue
		}

		for _, entry := range entries {
			if entry.IsDir() {
				continue
			}
			lower := strings.ToLower(entry.Name())
			if strings.HasSuffix(lower, ".exe") || strings.HasSuffix(lower, ".tmp") {
				fullPath := filepath.Join(dir, entry.Name())
				if rErr := os.Remove(fullPath); rErr != nil {
					errs = append(errs, fmt.Sprintf("cannot remove %s: %v", fullPath, rErr))
				}
			}
		}
	}

	if len(errs) > 0 {
		return errors.New(strings.Join(errs, "; "))
	}
	return nil
}

// DownloadInstaller downloads the installer file to a local updates folder with progress reporting.
func DownloadInstaller(ctx context.Context, downloadURL string, progressFn func(percent int)) (string, error) {
	if downloadURL == "" {
		return "", ErrNoInstallerAsset
	}

	updatesDir := GetUpdatesDir()
	if err := os.MkdirAll(updatesDir, 0755); err != nil {
		return "", fmt.Errorf("failed to create updates directory: %w", err)
	}

	// Purge any stale download files
	_ = CleanupOldInstallers()

	fileName := "BobrDobr-Setup.exe"
	if parsed, err := url.Parse(downloadURL); err == nil && parsed.Path != "" {
		base := path.Base(parsed.Path)
		if strings.HasSuffix(strings.ToLower(base), ".exe") {
			fileName = base
		}
		if fileName == "BobrDobr-Setup.exe" {
			re := regexp.MustCompile(`/v?(\d+\.\d+(\.\d+)?)`)
			if matches := re.FindStringSubmatch(parsed.Path); len(matches) > 1 {
				fileName = fmt.Sprintf("BobrDobr-Setup-v%s.exe", matches[1])
			}
		}
	}

	installerPath := filepath.Join(updatesDir, fileName)
	tempPath := installerPath + ".tmp"

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, downloadURL, nil)
	if err != nil {
		return "", fmt.Errorf("failed to create download request: %w", err)
	}
	req.Header.Set("User-Agent", UserAgent)

	client := &http.Client{Timeout: 10 * time.Minute}
	resp, err := client.Do(req)
	if err != nil {
		return "", fmt.Errorf("failed to download installer: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("download server returned HTTP %d", resp.StatusCode)
	}

	out, err := os.OpenFile(tempPath, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0755)
	if err != nil {
		return "", fmt.Errorf("failed to create temporary download file: %w", err)
	}

	if progressFn != nil {
		progressFn(0)
	}

	totalBytes := resp.ContentLength
	var downloaded int64
	buf := make([]byte, 32*1024)
	lastReportedPercent := 0

	for {
		select {
		case <-ctx.Done():
			out.Close()
			_ = os.Remove(tempPath)
			return "", ErrDownloadCancelled
		default:
		}

		n, rErr := resp.Body.Read(buf)
		if n > 0 {
			if _, wErr := out.Write(buf[:n]); wErr != nil {
				out.Close()
				_ = os.Remove(tempPath)
				return "", fmt.Errorf("failed writing installer data: %w", wErr)
			}
			downloaded += int64(n)

			if totalBytes > 0 && progressFn != nil {
				pct := int((downloaded * 100) / totalBytes)
				if pct > 100 {
					pct = 100
				}
				if pct != lastReportedPercent {
					lastReportedPercent = pct
					progressFn(pct)
				}
			}
		}

		if rErr != nil {
			if rErr == io.EOF {
				break
			}
			out.Close()
			_ = os.Remove(tempPath)
			return "", fmt.Errorf("error during installer download: %w", rErr)
		}
	}

	if err := out.Close(); err != nil {
		_ = os.Remove(tempPath)
		return "", fmt.Errorf("failed to close downloaded file: %w", err)
	}

	_ = os.Remove(installerPath)
	if err := os.Rename(tempPath, installerPath); err != nil {
		return "", fmt.Errorf("failed to finalize installer file: %w", err)
	}

	if progressFn != nil {
		progressFn(100)
	}

	return installerPath, nil
}

// LaunchInstallerAndExit executes the installer in upgrade mode and terminates the running client.
func LaunchInstallerAndExit(installerPath string, silent bool) error {
	if _, err := os.Stat(installerPath); err != nil {
		return fmt.Errorf("installer file not found: %w", err)
	}

	args := []string{"/UPDATE"}
	if silent {
		args = append(args, "/CLOSEAPPLICATIONS", "/SILENT", "/NORESTART")
	}

	cmd := exec.Command(installerPath, args...)
	cmd.Dir = filepath.Dir(installerPath)

	if err := cmd.Start(); err != nil {
		return fmt.Errorf("failed to launch installer: %w", err)
	}

	return nil
}
