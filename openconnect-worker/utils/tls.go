package utils

import (
	"context"
	"fmt"
	"net"
	"time"

	tls "github.com/refraction-networking/utls"
)

// DialBrowserTLS establishes a TLS connection using uTLS with Google Chrome fingerprint
// and custom ALPN strictly set to http/1.1 (required for CSTP / AnyConnect).
func DialBrowserTLS(ctx context.Context, targetAddr string, serverName string, insecure bool) (*tls.UConn, error) {
	dialer := &net.Dialer{Timeout: 10 * time.Second}
	rawConn, err := dialer.DialContext(ctx, "tcp", targetAddr)
	if err != nil {
		return nil, fmt.Errorf("tcp dial failed: %w", err)
	}

	sni := serverName
	if host, _, err := net.SplitHostPort(serverName); err == nil {
		sni = host
	}

	config := &tls.Config{
		ServerName:         sni,
		InsecureSkipVerify: insecure,
	}

	uConn := tls.UClient(rawConn, config, tls.HelloCustom)

	// Fetch Chrome fingerprint specification (GREASE, CipherSuites, Curves, Extensions)
	spec, err := tls.UTLSIdToSpec(tls.HelloChrome_Auto)
	if err != nil {
		rawConn.Close()
		return nil, fmt.Errorf("failed to generate chrome spec: %w", err)
	}

	// Override ALPN strictly to ["http/1.1"] to guarantee CSTP AnyConnect protocol compatibility
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

	if err := uConn.ApplyPreset(&spec); err != nil {
		rawConn.Close()
		return nil, fmt.Errorf("failed to apply chrome preset: %w", err)
	}

	if err := uConn.HandshakeContext(ctx); err != nil {
		uConn.Close()
		return nil, fmt.Errorf("tls handshake failed: %w", err)
	}

	return uConn, nil
}
