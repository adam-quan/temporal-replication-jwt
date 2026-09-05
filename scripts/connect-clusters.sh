#!/usr/bin/env bash
#
# Joins cluster-a and cluster-b into a replication pair and creates a global
# namespace that lives on both.
#
# Run from the repo root, after both stacks are up:
#
#   docker compose up -d
#   docker compose -f docker-compose.cluster-b.yml up -d
#   ./scripts/connect-clusters.sh
#
# Remote clusters are deliberately not listed in either config.yaml: the server
# logs "All remote cluster settings under ClusterMetadata.ClusterInformation
# config will be ignored" and reads them from the cluster_metadata table
# instead. `temporal operator cluster upsert` is what writes that table.
#
# There are two different addresses in play, and mixing them up is the usual
# way this goes wrong:
#
#   * This script's own operator calls go to each cluster's *public* frontend
#     (7233) and carry a Keycloak JWT, exactly like any other client.
#   * The address each cluster *registers* for its peer is that peer's public
#     frontend too, and it must match the rpcAddress that peer advertises in
#     its own config.yaml. It has to be the listener that runs the JWT claim
#     mapper, because a token is replication's only credential.
set -euo pipefail

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
A_SERVER_NAME=${A_SERVER_NAME:-temporal}
B_SERVER_NAME=${B_SERVER_NAME:-temporal-b}

GLOBAL_NAMESPACE=${GLOBAL_NAMESPACE:-replicated}

# Keycloak is published on the host, so the token is minted here and passed to
# the containerised CLI. Re-minted per call: the retry loops below can outlast
# a five-minute access token.
fetch_token() {
  curl -sf -X POST \
    "$KEYCLOAK_URL/realms/$KEYCLOAK_REALM/protocol/openid-connect/token" \
    -d grant_type=client_credentials \
    -d "client_id=$KEYCLOAK_CLIENT_ID" \
    -d "client_secret=$KEYCLOAK_CLIENT_SECRET" \
    | python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["access_token"])'
}

# tctl <cluster-a|cluster-b> <temporal args...>
tctl() {
  local cluster=$1; shift
  local addr name token
  case $cluster in
    cluster-a) addr=$A_ADDR; name=$A_SERVER_NAME ;;
    cluster-b) addr=$B_ADDR; name=$B_SERVER_NAME ;;
    *) echo "unknown cluster: $cluster" >&2; return 1 ;;
  esac
  token=$(fetch_token)
  docker run --rm --network "$NETWORK" \
    -v "$ROOT_DIR/certs:/certs:ro" \
    "$ADMIN_TOOLS_IMAGE" temporal "$@" \
    --address "$addr" \
    --tls \
    --tls-ca-path /certs/ca/ca.pem \
    --tls-server-name "$name" \
    --grpc-meta authorization="Bearer $token"
}

wait_for() {
  local cluster=$1
  echo "Waiting for $cluster..."
  for _ in $(seq 1 60); do
    if tctl "$cluster" operator cluster health >/dev/null 2>&1; then
      echo "  $cluster is up"
      return 0
    fi
    sleep 5
  done
  echo "  $cluster did not become reachable" >&2
  return 1
}

wait_for cluster-a
wait_for cluster-b

# Each side registers the other. --enable-connection makes the peer visible;
# --enable-replication turns on the stream that actually moves data.
#
# This upsert is also the first end-to-end test of the JWT path: the receiving
# cluster immediately dials the address given here and calls DescribeCluster on
# it over TLS with a bearer token from its TokenProvider. A misconfigured token
# provider fails right here rather than silently stalling later.
echo
echo "Registering cluster-b with cluster-a..."
tctl cluster-a operator cluster upsert --frontend-address "$B_ADDR" --enable-connection --enable-replication

echo "Registering cluster-a with cluster-b..."
tctl cluster-b operator cluster upsert --frontend-address "$A_ADDR" --enable-connection --enable-replication

echo
echo "cluster-a sees:"
tctl cluster-a operator cluster list
echo "cluster-b sees:"
tctl cluster-b operator cluster list

# A global namespace is created once, on its active cluster, and propagates to
# the other side over the replication stream a moment later.
#
# The retry is not decoration: each frontend caches the cluster list and
# refreshes it on system.clusterMetadataRefreshInterval (a minute by default),
# so for a short window after the upsert above cluster-a still rejects
# cluster-b with "Invalid cluster name".
echo
if tctl cluster-a operator namespace describe -n "$GLOBAL_NAMESPACE" >/dev/null 2>&1; then
  echo "Global namespace '$GLOBAL_NAMESPACE' already exists"
else
  echo "Creating global namespace '$GLOBAL_NAMESPACE' (active: cluster-a)..."
  created=false
  for attempt in $(seq 1 18); do
    if tctl cluster-a operator namespace create \
        -n "$GLOBAL_NAMESPACE" \
        --global \
        --cluster cluster-a \
        --cluster cluster-b \
        --active-cluster cluster-a >/tmp/xdc-ns-create.log 2>&1; then
      created=true
      break
    fi
    if ! grep -q "Invalid cluster name" /tmp/xdc-ns-create.log; then
      echo "  namespace creation failed:" >&2
      cat /tmp/xdc-ns-create.log >&2
      exit 1
    fi
    echo "  cluster list not refreshed on cluster-a yet, retrying ($attempt/18)..."
    sleep 10
  done
  if [ "$created" != true ]; then
    echo "  namespace creation never succeeded; last output:" >&2
    cat /tmp/xdc-ns-create.log >&2
    exit 1
  fi
  echo "  created"
fi

echo
echo "Waiting for '$GLOBAL_NAMESPACE' to replicate to cluster-b..."
for _ in $(seq 1 30); do
  if tctl cluster-b operator namespace describe -n "$GLOBAL_NAMESPACE" >/dev/null 2>&1; then
    echo "  replicated"
    tctl cluster-b operator namespace describe -n "$GLOBAL_NAMESPACE"
    echo
    echo "Both clusters are connected. Next: ./scripts/verify-replication.sh"
    exit 0
  fi
  sleep 5
done

echo "  '$GLOBAL_NAMESPACE' has not appeared on cluster-b yet; check the server logs:" >&2
echo "    docker compose logs temporal | grep -i replicat" >&2
exit 1
