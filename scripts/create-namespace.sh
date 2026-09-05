#!/bin/sh
#
# Waits for one cluster's public frontend and creates the `default` namespace
# on it. Run as a one-shot container by both compose files.
#
# Every call here goes to the public frontend, which validates a JWT, so each
# one carries a bearer token minted by scripts/token.sh. The token is re-minted
# per attempt rather than once up front: these retry loops can outlast a
# Keycloak access token, and a stale token looks like a permission error rather
# than an expiry.
set -eu

NAMESPACE=${DEFAULT_NAMESPACE:-default}
TEMPORAL_ADDRESS=${TEMPORAL_ADDRESS:-temporal:7233}
MAX_ATTEMPTS=${TEMPORAL_HEALTH_CHECK_MAX_ATTEMPTS:-30}
SLEEP_SECONDS=${TEMPORAL_HEALTH_CHECK_SLEEP_SECONDS:-5}

: "${KEYCLOAK_CLIENT_SECRET:?KEYCLOAK_CLIENT_SECRET must be set (run ./scripts/setup-keycloak.sh)}"

# The frontend serves TLS but asks for no client certificate, so all the CLI
# needs is the CA to verify the server with - the JWT is what identifies the
# caller. Passed explicitly rather than relying on the CLI picking up the
# TEMPORAL_TLS_* variables, so the flags stay visible when something breaks.
TLS_ARGS=""
if [ -n "${TEMPORAL_TLS_CA_PATH:-}" ]; then
  TLS_ARGS="--tls --tls-ca-path $TEMPORAL_TLS_CA_PATH \
    --tls-server-name ${TEMPORAL_TLS_SERVER_NAME:-temporal}"
fi

fetch_token() { /scripts/token.sh 2>/dev/null || true; }

echo 'Waiting for Keycloak to issue a token...'
attempt=1
while :; do
  TOKEN=$(fetch_token)
  if [ -n "$TOKEN" ]; then
    echo 'Obtained JWT from Keycloak'
    break
  fi
  if [ "$attempt" -ge "$MAX_ATTEMPTS" ]; then
    echo "Could not obtain a JWT from Keycloak after $MAX_ATTEMPTS attempts"
    exit 1
  fi
  echo "Keycloak not ready yet, waiting... (attempt $attempt/$MAX_ATTEMPTS)"
  attempt=$((attempt + 1))
  sleep "$SLEEP_SECONDS"
done

echo "Waiting for Temporal server port to be available..."
SERVER_HOST=$(echo "$TEMPORAL_ADDRESS" | cut -d: -f1)
SERVER_PORT=$(echo "$TEMPORAL_ADDRESS" | cut -d: -f2)
attempt=1
while ! nc -z -w 10 "$SERVER_HOST" "$SERVER_PORT"; do
  if [ "$attempt" -ge "$MAX_ATTEMPTS" ]; then
    echo "Temporal server port did not become available after $MAX_ATTEMPTS attempts"
    exit 1
  fi
  echo "Temporal server port not ready yet, waiting... (attempt $attempt/$MAX_ATTEMPTS)"
  attempt=$((attempt + 1))
  sleep "$SLEEP_SECONDS"
done
echo 'Temporal server port is available'

echo 'Waiting for Temporal server to be healthy...'
attempt=1
while :; do
  TOKEN=$(fetch_token)
  if [ -n "$TOKEN" ] && temporal operator cluster health \
      --address "$TEMPORAL_ADDRESS" $TLS_ARGS \
      --grpc-meta authorization="Bearer $TOKEN"; then
    break
  fi
  if [ "$attempt" -ge "$MAX_ATTEMPTS" ]; then
    echo "Server did not become healthy after $MAX_ATTEMPTS attempts"
    exit 1
  fi
  echo "Server not ready yet, waiting... (attempt $attempt/$MAX_ATTEMPTS)"
  attempt=$((attempt + 1))
  sleep "$SLEEP_SECONDS"
done

echo "Server is healthy, creating namespace '$NAMESPACE'..."
attempt=1
while :; do
  TOKEN=$(fetch_token)

  if [ -n "$TOKEN" ] && temporal operator namespace describe -n "$NAMESPACE" \
      --address "$TEMPORAL_ADDRESS" $TLS_ARGS \
      --grpc-meta authorization="Bearer $TOKEN" >/dev/null 2>&1; then
    echo "Namespace '$NAMESPACE' already exists"
    break
  fi

  if [ -n "$TOKEN" ] && temporal operator namespace create -n "$NAMESPACE" \
      --address "$TEMPORAL_ADDRESS" $TLS_ARGS \
      --grpc-meta authorization="Bearer $TOKEN" >/dev/null 2>&1; then
    echo "Namespace '$NAMESPACE' created"
    break
  fi

  if [ "$attempt" -ge "$MAX_ATTEMPTS" ]; then
    echo "Failed to create namespace '$NAMESPACE' after $MAX_ATTEMPTS attempts"
    exit 1
  fi

  echo "Namespace operation not ready yet, waiting... (attempt $attempt/$MAX_ATTEMPTS)"
  attempt=$((attempt + 1))
  sleep "$SLEEP_SECONDS"
done
