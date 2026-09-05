package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strings"
	"sync"
	"time"

	"go.temporal.io/server/common/log"
	"go.temporal.io/server/common/log/tag"
	"go.temporal.io/server/common/rpc/auth"
)

// oidcTokenProvider is the TokenProvider plugin that secures cluster replication
// traffic. The server calls GetToken on every outbound cross-cluster RPC, so the
// cache below is not an optimisation - without it every replication task would
// become a round trip to Keycloak.
//
// The grant is client_credentials: replication has no user behind it, so the
// cluster authenticates as the service account of its own OIDC client. That
// client's token carries `permissions: ["temporal-system:admin"]`, which is what
// the receiving cluster's default authorizer needs to admit AdminService calls
// such as StreamWorkflowReplicationMessages.
type oidcTokenProvider struct {
	tokenURL     string
	clientID     string
	clientSecret string
	scope        string
	audience     string
	// refreshSkew is how long before expiry a cached token is considered stale.
	refreshSkew time.Duration

	httpClient *http.Client
	logger     log.Logger

	mu      sync.Mutex
	token   string
	expires time.Time
	// inflight collapses concurrent refreshes into one request. Replication opens
	// many streams at once on startup and on reconnect, and without this every one
	// of them would hit Keycloak with its own token request.
	inflight *sync.WaitGroup
}

var _ auth.TokenProvider = (*oidcTokenProvider)(nil)

// newOIDCTokenProviderFromEnv builds the provider from the environment, or
// returns nil when no token URL is configured. A nil provider means the server
// sends no auth header on cross-cluster RPCs, which is the pre-JWT behaviour.
func newOIDCTokenProviderFromEnv(logger log.Logger) (*oidcTokenProvider, error) {
	tokenURL := strings.TrimSpace(os.Getenv("TEMPORAL_XDC_OIDC_TOKEN_URL"))
	if tokenURL == "" {
		return nil, nil
	}

	clientID := strings.TrimSpace(os.Getenv("TEMPORAL_XDC_OIDC_CLIENT_ID"))
	clientSecret := os.Getenv("TEMPORAL_XDC_OIDC_CLIENT_SECRET")
	if clientID == "" || clientSecret == "" {
		return nil, fmt.Errorf(
			"TEMPORAL_XDC_OIDC_TOKEN_URL is set, so TEMPORAL_XDC_OIDC_CLIENT_ID and " +
				"TEMPORAL_XDC_OIDC_CLIENT_SECRET must be set too")
	}

	skew := 30 * time.Second
	if v := strings.TrimSpace(os.Getenv("TEMPORAL_XDC_OIDC_REFRESH_SKEW")); v != "" {
		parsed, err := time.ParseDuration(v)
		if err != nil {
			return nil, fmt.Errorf("invalid TEMPORAL_XDC_OIDC_REFRESH_SKEW %q: %w", v, err)
		}
		skew = parsed
	}

	return &oidcTokenProvider{
		tokenURL:     tokenURL,
		clientID:     clientID,
		clientSecret: clientSecret,
		scope:        strings.TrimSpace(os.Getenv("TEMPORAL_XDC_OIDC_SCOPE")),
		audience:     strings.TrimSpace(os.Getenv("TEMPORAL_XDC_OIDC_AUDIENCE")),
		refreshSkew:  skew,
		httpClient:   &http.Client{Timeout: 10 * time.Second},
		logger:       logger,
	}, nil
}

// GetToken returns a cached access token, minting a new one when the cached one
// is within refreshSkew of expiry. rpcAddress is ignored: both peers accept the
// same service-account token. Scoping per receiver would mean one OIDC client
// per peer, which is the shape to reach for if the clusters ever stop trusting
// each other symmetrically.
func (p *oidcTokenProvider) GetToken(ctx context.Context, rpcAddress string) (string, error) {
	for {
		p.mu.Lock()
		if p.token != "" && time.Now().Before(p.expires.Add(-p.refreshSkew)) {
			token := p.token
			p.mu.Unlock()
			return token, nil
		}
		if wg := p.inflight; wg != nil {
			// Another caller is already fetching; wait for it rather than piling
			// a second request onto Keycloak, then re-check the cache.
			p.mu.Unlock()
			done := make(chan struct{})
			go func() {
				wg.Wait()
				close(done)
			}()
			select {
			case <-done:
				continue
			case <-ctx.Done():
				return "", ctx.Err()
			}
		}

		wg := &sync.WaitGroup{}
		wg.Add(1)
		p.inflight = wg
		p.mu.Unlock()

		token, expiresIn, err := p.fetch(ctx)

		p.mu.Lock()
		p.inflight = nil
		if err == nil {
			p.token = token
			p.expires = time.Now().Add(expiresIn)
		}
		p.mu.Unlock()
		wg.Done()

		if err != nil {
			p.logger.Error("Failed to mint replication token", tag.Address(rpcAddress), tag.Error(err))
			return "", err
		}
		return token, nil
	}
}

func (p *oidcTokenProvider) fetch(ctx context.Context) (string, time.Duration, error) {
	form := url.Values{
		"grant_type":    {"client_credentials"},
		"client_id":     {p.clientID},
		"client_secret": {p.clientSecret},
	}
	if p.scope != "" {
		form.Set("scope", p.scope)
	}
	if p.audience != "" {
		form.Set("audience", p.audience)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, p.tokenURL, strings.NewReader(form.Encode()))
	if err != nil {
		return "", 0, err
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

	resp, err := p.httpClient.Do(req)
	if err != nil {
		return "", 0, fmt.Errorf("token request to %s failed: %w", p.tokenURL, err)
	}
	defer func() { _ = resp.Body.Close() }()

	body, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if err != nil {
		return "", 0, fmt.Errorf("reading token response: %w", err)
	}
	if resp.StatusCode != http.StatusOK {
		return "", 0, fmt.Errorf("token endpoint %s returned %s: %s", p.tokenURL, resp.Status, strings.TrimSpace(string(body)))
	}

	var payload struct {
		AccessToken string `json:"access_token"`
		ExpiresIn   int64  `json:"expires_in"`
	}
	if err := json.Unmarshal(body, &payload); err != nil {
		return "", 0, fmt.Errorf("decoding token response: %w", err)
	}
	if payload.AccessToken == "" {
		return "", 0, fmt.Errorf("token endpoint %s returned no access_token", p.tokenURL)
	}

	// Some providers omit expires_in. A short assumed lifetime is the safe
	// default: the worst case is an extra token request, not a rejected RPC.
	expiresIn := time.Duration(payload.ExpiresIn) * time.Second
	if expiresIn <= 0 {
		expiresIn = time.Minute
	}
	return payload.AccessToken, expiresIn, nil
}
