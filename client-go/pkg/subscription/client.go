package subscription

import (
	"context"
	"crypto/tls"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

var (
	ErrEmptyURL         = errors.New("subscription URL cannot be empty")
	ErrInvalidURL       = errors.New("invalid subscription URL")
	ErrUnauthorized     = errors.New("subscription token is invalid or revoked")
	ErrForbidden        = errors.New("subscription access forbidden: blocked or expired")
	ErrNotFound         = errors.New("subscription profile or server not found (404)")
	ErrRateLimited      = errors.New("rate limit exceeded, please wait before retrying")
	ErrServerInternal   = errors.New("subscription server error")
	ErrNoProfilesFound  = errors.New("subscription contains no valid connection profiles")
)

// ClientOption configures the Subscription Client.
type ClientOption func(*Client)

// WithHTTPClient sets a custom HTTP client.
func WithHTTPClient(httpClient *http.Client) ClientOption {
	return func(c *Client) {
		c.httpClient = httpClient
	}
}

// WithUserAgent sets a custom User-Agent string.
func WithUserAgent(ua string) ClientOption {
	return func(c *Client) {
		c.userAgent = ua
	}
}

// WithTimeout sets a custom request timeout.
func WithTimeout(timeout time.Duration) ClientOption {
	return func(c *Client) {
		c.timeout = timeout
		if c.httpClient != nil {
			c.httpClient.Timeout = timeout
		}
	}
}

// WithMaxRetries configures maximum retry attempts for HTTP 429.
func WithMaxRetries(retries int) ClientOption {
	return func(c *Client) {
		c.maxRetries = retries
	}
}

// Client manages subscription fetching, parsing, and lifecycle verification.
type Client struct {
	httpClient     *http.Client
	userAgent      string
	timeout        time.Duration
	maxRetries     int
	retryBaseDelay time.Duration
}

// NewClient creates a new subscription client with modern TLS defaults.
func NewClient(opts ...ClientOption) *Client {
	c := &Client{
		userAgent:      "BobrDobr-VPN/1.1.0",
		timeout:        15 * time.Second,
		maxRetries:     3,
		retryBaseDelay: 500 * time.Millisecond,
	}

	transport := &http.Transport{
		TLSClientConfig: &tls.Config{
			MinVersion: tls.VersionTLS12,
		},
		ForceAttemptHTTP2:   true,
		MaxIdleConns:        10,
		IdleConnTimeout:     30 * time.Second,
		TLSHandshakeTimeout: 10 * time.Second,
	}

	c.httpClient = &http.Client{
		Transport: transport,
		Timeout:   c.timeout,
	}

	for _, opt := range opts {
		opt(c)
	}

	return c
}

// NormalizeURL cleans and ensures standard https:// scheme for subscription links.
func NormalizeURL(rawURL string) (string, error) {
	trimmed := strings.TrimSpace(rawURL)
	if trimmed == "" {
		return "", ErrEmptyURL
	}

	if !strings.HasPrefix(trimmed, "http://") && !strings.HasPrefix(trimmed, "https://") {
		trimmed = "https://" + trimmed
	}

	parsed, err := url.ParseRequestURI(trimmed)
	if err != nil || parsed.Host == "" {
		return "", fmt.Errorf("%w: '%s'", ErrInvalidURL, rawURL)
	}

	return parsed.String(), nil
}

// FetchSubscription retrieves and parses subscription profiles from a remote provider.
func (c *Client) FetchSubscription(ctx context.Context, subURL string) (*SubscriptionInfo, error) {
	targetURL, err := NormalizeURL(subURL)
	if err != nil {
		return nil, err
	}

	var resp *http.Response
	var lastErr error

	for attempt := 0; attempt <= c.maxRetries; attempt++ {
		req, err := http.NewRequestWithContext(ctx, http.MethodGet, targetURL, nil)
		if err != nil {
			return nil, fmt.Errorf("failed to create http request: %w", err)
		}

		req.Header.Set("Accept", "application/json")
		req.Header.Set("User-Agent", c.userAgent)

		resp, err = c.httpClient.Do(req)
		if err != nil {
			return nil, fmt.Errorf("network error connecting to subscription server: %w", err)
		}

		if resp.StatusCode == http.StatusTooManyRequests {
			_ = resp.Body.Close()
			if attempt < c.maxRetries {
				sleepDuration := c.retryBaseDelay * (1 << attempt)
				if retryAfter := resp.Header.Get("Retry-After"); retryAfter != "" {
					if sec, err := strconv.Atoi(retryAfter); err == nil && sec > 0 {
						sleepDuration = time.Duration(sec) * time.Second
					}
				}
				select {
				case <-time.After(sleepDuration):
					continue
				case <-ctx.Done():
					return nil, ctx.Err()
				}
			}
			return nil, ErrRateLimited
		}

		break
	}

	defer resp.Body.Close()

	bodyBytes, err := io.ReadAll(io.LimitReader(resp.Body, 10*1024*1024)) // 10MB safety cap
	if err != nil {
		return nil, fmt.Errorf("failed to read response body: %w", err)
	}

	// Status code handling
	switch {
	case resp.StatusCode == http.StatusOK:
		// Success, continue parsing below
	case resp.StatusCode == http.StatusUnauthorized:
		return nil, ErrUnauthorized
	case resp.StatusCode == http.StatusForbidden:
		bodyLower := strings.ToLower(string(bodyBytes))
		if strings.Contains(bodyLower, "expire") || strings.Contains(bodyLower, "истек") || strings.Contains(bodyLower, "истёк") {
			return nil, fmt.Errorf("%w: expired", ErrForbidden)
		}
		return nil, fmt.Errorf("%w: blocked or unauthorized", ErrForbidden)
	case resp.StatusCode == http.StatusNotFound:
		return nil, ErrNotFound
	case resp.StatusCode >= 500:
		return nil, fmt.Errorf("%w (code %d)", ErrServerInternal, resp.StatusCode)
	default:
		return nil, fmt.Errorf("subscription request failed with HTTP code %d", resp.StatusCode)
	}

	userinfo := resp.Header.Get("Subscription-Userinfo")
	info, err := DecodeSubscriptionPayload(bodyBytes, targetURL, userinfo)
	if err != nil {
		return nil, err
	}

	_ = lastErr
	return info, nil
}

// ValidateSubscriptionURL tests connectivity and validates that the URL produces valid profiles.
func (c *Client) ValidateSubscriptionURL(ctx context.Context, rawURL string) error {
	info, err := c.FetchSubscription(ctx, rawURL)
	if err != nil {
		return err
	}

	if len(info.Profiles) == 0 && info.Status != StatusExpired && info.Status != StatusBlocked {
		return ErrNoProfilesFound
	}

	return nil
}
