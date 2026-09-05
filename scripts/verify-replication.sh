#!/usr/bin/env bash
#
# End-to-end check of the whole stack. Run from the repo root after
# ./scripts/connect-clusters.sh:
#
#   ./scripts/verify-replication.sh
#
# Six checks, in order of what they would tell you if they failed:
#
#   1. the TokenProvider is compiled in and enabled on both servers
#   2. both public frontends are reachable over TLS with a JWT
#   3. the public frontend rejects a call with no JWT
#   4. each cluster sees the other, with connection and replication on
#   5. the global namespace exists on both clusters
#   6. a workflow started on cluster-a shows up on cluster-b
#
# Check 6 needs no worker: an unstarted workflow still has a history, and it is
# that history crossing the replication stream that is being tested.
# Deliberately no `pipefail`: nearly every check below is a `... | grep -q`,
# and grep -q exits the moment it matches, so the producer takes a SIGPIPE that
# pipefail would report as a failed pipeline.
set -u

ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
NETWORK=${NETWORK:-temporal-network}

# shellcheck disable=SC1091
[ -f "$ROOT_DIR/.env" ] && set -a && . "$ROOT_DIR/.env" && set +a

ADMIN_TOOLS_IMAGE=${ADMIN_TOOLS_IMAGE:-temporalio/admin-tools:${TEMPORAL_ADMINTOOLS_VERSION:-1.31.0}}

KEYCLOAK_URL=${KEYCLOAK_URL:-http://localhost:9080}
KEYCLOAK_REALM=${KEYCLOAK_REALM:-temporal}
KEYCLOAK_CLIENT_ID=${KEYCLOAK_CLIENT_ID:-temporal-app}
: "${KEYCLOAK_CLIENT_SECRET:?KEYCLOAK_CLIENT_SECRET is not set - run ./scripts/setup-keycloak.sh}"

A_ADDR=${A_ADDR:-temporal:7233}
B_ADDR=${B_ADDR:-temporal-b:7233}
GLOBAL_NAMESPACE=${GLOBAL_NAMESPACE:-replicated}

pass=0
fail=0
ok()   { printf '  \033[32mPASS\033[0m %s\n' "$1"; pass=$((pass + 1)); }
bad()  { printf '  \033[31mFAIL\033[0m %s\n' "$1"; fail=$((fail + 1)); }
head_() { printf '\n\033[1m%s\033[0m\n' "$1"; }

fetch_token() {
  curl -sf -X POST \
    "$KEYCLOAK_URL/realms/$KEYCLOAK_REALM/protocol/openid-connect/token" \
    -d grant_type=client_credentials \
    -d "client_id=$KEYCLOAK_CLIENT_ID" \
    -d "client_secret=$KEYCLOAK_CLIENT_SECRET" \
    | python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["access_token"])'
}

# tctl <cluster-a|cluster-b> <temporal args...>  - authenticated, over TLS
tctl() {
  local cluster=$1; shift
  local addr name token
  case $cluster in
    cluster-a) addr=$A_ADDR; name=temporal ;;
    cluster-b) addr=$B_ADDR; name=temporal-b ;;
  esac
  token=$(fetch_token)
  docker run --rm --network "$NETWORK" -v "$ROOT_DIR/certs:/certs:ro" \
    "$ADMIN_TOOLS_IMAGE" temporal "$@" \
    --address "$addr" --tls --tls-ca-path /certs/ca/ca.pem \
    --tls-server-name "$name" \
    --grpc-meta authorization="Bearer $token"
}

# Same, with no Authorization header at all.
tctl_anon() {
  local cluster=$1; shift
  local addr name
  case $cluster in
    cluster-a) addr=$A_ADDR; name=temporal ;;
    cluster-b) addr=$B_ADDR; name=temporal-b ;;
  esac
  docker run --rm --network "$NETWORK" -v "$ROOT_DIR/certs:/certs:ro" \
    "$ADMIN_TOOLS_IMAGE" temporal "$@" \
    --address "$addr" --tls --tls-ca-path /certs/ca/ca.pem \
    --tls-server-name "$name"
}

# ---------------------------------------------------------------------------
head_ "1. TokenProvider enabled on both servers"
# main.go logs this line only when TEMPORAL_XDC_OIDC_TOKEN_URL resolved into a
# provider that was handed to temporal.WithTokenProvider.
for pair in "temporal:cluster-a" "temporal-b:cluster-b"; do
  container=${pair%%:*}; label=${pair##*:}
  logs=$(docker logs "$container" 2>&1) || true
  if printf '%s' "$logs" | grep -q "Replication token provider enabled"; then
    ok "$label: server logged \"Replication token provider enabled\""
  else
    bad "$label: no TokenProvider in the log - is TEMPORAL_XDC_OIDC_TOKEN_URL set?"
  fi
done

# ---------------------------------------------------------------------------
head_ "2. Public frontends reachable over TLS with a JWT"
for c in cluster-a cluster-b; do
  if tctl "$c" operator cluster health >/dev/null 2>&1; then
    ok "$c: healthy"
  else
    bad "$c: cluster health failed"
  fi
done

# ---------------------------------------------------------------------------
head_ "3. Public frontends reject a call with no JWT"
# The default claim mapper turns a missing token into empty claims, and the
# default authorizer denies from there. A PASS here is what makes the JWT the
# credential rather than decoration.
for c in cluster-a cluster-b; do
  out=$(tctl_anon "$c" operator namespace list 2>&1)
  status=$?
  if [ "$status" -eq 0 ]; then
    bad "$c: unauthenticated call SUCCEEDED - authorization is not being enforced"
  elif printf '%s' "$out" | grep -qi "permission denied\|unauthenticated\|request unauthorized"; then
    ok "$c: unauthenticated call denied"
  else
    bad "$c: call failed, but not with an auth error: $(printf '%s' "$out" | head -1)"
  fi
done

# ---------------------------------------------------------------------------
head_ "4. Each cluster sees the other, connection and replication on"
for pair in "cluster-a:cluster-b" "cluster-b:cluster-a"; do
  local_c=${pair%%:*}; remote_c=${pair##*:}
  listing=$(tctl "$local_c" operator cluster list 2>&1)
  if printf '%s' "$listing" | grep -q "$remote_c"; then
    ok "$local_c: sees $remote_c"
  else
    bad "$local_c: does not see $remote_c - re-run ./scripts/connect-clusters.sh"
  fi
done
echo
echo "  cluster-a's view:"
tctl cluster-a operator cluster list 2>&1 | sed 's/^/    /'
echo "  cluster-b's view:"
tctl cluster-b operator cluster list 2>&1 | sed 's/^/    /'

# ---------------------------------------------------------------------------
head_ "5. Global namespace '$GLOBAL_NAMESPACE' present on both clusters"
for c in cluster-a cluster-b; do
  if tctl "$c" operator namespace describe -n "$GLOBAL_NAMESPACE" >/dev/null 2>&1; then
    ok "$c: has '$GLOBAL_NAMESPACE'"
  else
    bad "$c: missing '$GLOBAL_NAMESPACE'"
  fi
done

# ---------------------------------------------------------------------------
head_ "6. A workflow started on cluster-a appears on cluster-b"
WF_ID="xdc-check-$(date +%s)"
if tctl cluster-a workflow start \
      --namespace "$GLOBAL_NAMESPACE" \
      --workflow-id "$WF_ID" \
      --type ReplicationCheck \
      --task-queue xdc-check >/dev/null 2>&1; then
  ok "cluster-a: started workflow $WF_ID"

  replicated=false
  for _ in $(seq 1 30); do
    if tctl cluster-b workflow describe \
        --namespace "$GLOBAL_NAMESPACE" --workflow-id "$WF_ID" >/dev/null 2>&1; then
      replicated=true
      break
    fi
    sleep 2
  done

  if [ "$replicated" = true ]; then
    ok "cluster-b: $WF_ID replicated across the JWT-secured stream"
    echo
    echo "  as cluster-b sees it:"
    tctl cluster-b workflow describe \
      --namespace "$GLOBAL_NAMESPACE" --workflow-id "$WF_ID" 2>&1 | head -12 | sed 's/^/    /'
  else
    bad "cluster-b: $WF_ID never arrived (waited 60s)"
    echo "    check the replication stream:"
    echo "      docker logs temporal 2>&1 | grep -i 'replicat\\|token'"
    echo "      docker logs temporal-b 2>&1 | grep -i 'replicat\\|token'"
  fi
else
  bad "cluster-a: could not start a workflow in '$GLOBAL_NAMESPACE'"
fi

# ---------------------------------------------------------------------------
printf '\n\033[1m%d passed, %d failed\033[0m\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
