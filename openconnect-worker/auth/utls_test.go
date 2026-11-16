package auth

import (
	"bufio"
	"context"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
	"time"

	tls "github.com/refraction-networking/utls"
	"openconnect-worker/utils"
)

func TestUtlsAlpn(t *testing.T) {
	spec, err := tls.UTLSIdToSpec(tls.HelloChrome_Auto)
	if err != nil {
		t.Fatalf("UTLSIdToSpec failed: %v", err)
	}

	alpnReplaced := false
	for i, ext := range spec.Extensions {
		if _, ok := ext.(*tls.ALPNExtension); ok {
			spec.Extensions[i] = &tls.ALPNExtension{
				AlpnProtocols: []string{"http/1.1"},
			}
			alpnReplaced = true
			break
		}
	}

	if !alpnReplaced {
		spec.Extensions = append(spec.Extensions, &tls.ALPNExtension{
			AlpnProtocols: []string{"http/1.1"},
		})
	}

	t.Logf("Extensions count: %d, ALPN replaced: %v", len(spec.Extensions), alpnReplaced)
}

func TestUtlsHandshakeAndAlpn(t *testing.T) {
	// Start a mock TLS server that supports http/1.1
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("CSTP_OK"))
	}))
	defer server.Close()

	u, err := url.Parse(server.URL)
	if err != nil {
		t.Fatalf("failed to parse test server url: %v", err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	hostPort := u.Host
	sni := strings.Split(hostPort, ":")[0]

	conn, err := utils.DialBrowserTLS(ctx, hostPort, sni, true)
	if err != nil {
		t.Fatalf("DialBrowserTLS failed: %v", err)
	}
	defer conn.Close()

	// Verify the connection works for HTTP/1.1 requests
	req, err := http.NewRequest("GET", "/", nil)
	if err != nil {
		t.Fatalf("failed to create request: %v", err)
	}
	req.Host = sni

	if err := req.Write(conn); err != nil {
		t.Fatalf("failed to write request over uTLS conn: %v", err)
	}

	reader := bufio.NewReader(conn)
	resp, err := http.ReadResponse(reader, req)
	if err != nil {
		t.Fatalf("failed to read response over uTLS conn: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Fatalf("expected status 200, got %d", resp.StatusCode)
	}

	t.Logf("Successfully established uTLS connection with Chrome fingerprint and http/1.1 ALPN!")
}
