package main

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"go.temporal.io/server/common/log"
)

func newTestProvider(t *testing.T, handler http.HandlerFunc) (*oidcTokenProvider, *httptest.Server) {
	t.Helper()
	srv := httptest.NewServer(handler)
	t.Cleanup(srv.Close)
	return &oidcTokenProvider{
		tokenURL:     srv.URL,
		clientID:     "temporal-replication",
		clientSecret: "secret",
		refreshSkew:  30 * time.Second,
		httpClient:   srv.Client(),
		logger:       log.NewTestLogger(),
	}, srv
}

func TestGetTokenCachesUntilNearExpiry(t *testing.T) {
	var calls atomic.Int64
	p, _ := newTestProvider(t, func(w http.ResponseWriter, r *http.Request) {
		n := calls.Add(1)
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintf(w, `{"access_token":"token-%d","expires_in":300}`, n)
	})

	for i := 0; i < 5; i++ {
		token, err := p.GetToken(context.Background(), "temporal-b:7233")
		if err != nil {
			t.Fatalf("GetToken: %v", err)
		}
		if token != "token-1" {
			t.Fatalf("got %q, want the cached token-1", token)
		}
	}
	if got := calls.Load(); got != 1 {
		t.Fatalf("token endpoint hit %d times, want 1", got)
	}

	// Inside the refresh skew: the cached token is still valid but too close to
	// expiry to hand out, so the next call must re-mint.
	p.expires = time.Now().Add(10 * time.Second)
	token, err := p.GetToken(context.Background(), "temporal-b:7233")
	if err != nil {
		t.Fatalf("GetToken after skew: %v", err)
	}
	if token != "token-2" {
		t.Fatalf("got %q, want a freshly minted token-2", token)
	}
}

func TestGetTokenCollapsesConcurrentRefreshes(t *testing.T) {
	var calls atomic.Int64
	release := make(chan struct{})
	p, _ := newTestProvider(t, func(w http.ResponseWriter, r *http.Request) {
		calls.Add(1)
		<-release
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprint(w, `{"access_token":"token","expires_in":300}`)
	})

	var wg sync.WaitGroup
	for i := 0; i < 20; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			if _, err := p.GetToken(context.Background(), "temporal-b:7233"); err != nil {
				t.Errorf("GetToken: %v", err)
			}
		}()
	}
	// Give the goroutines time to pile up on the in-flight request.
	time.Sleep(100 * time.Millisecond)
	close(release)
	wg.Wait()

	if got := calls.Load(); got != 1 {
		t.Fatalf("token endpoint hit %d times, want 1", got)
	}
}

func TestGetTokenSurfacesEndpointErrors(t *testing.T) {
	p, _ := newTestProvider(t, func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, `{"error":"invalid_client"}`, http.StatusUnauthorized)
	})

	if _, err := p.GetToken(context.Background(), "temporal-b:7233"); err == nil {
		t.Fatal("expected an error from a 401 token endpoint")
	}

	// A failed refresh must not poison the provider: the next call retries.
	if _, err := p.GetToken(context.Background(), "temporal-b:7233"); err == nil {
		t.Fatal("expected the retry to fail too")
	}
}
