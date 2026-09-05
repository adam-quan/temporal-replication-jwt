#!/usr/bin/env bash
#
# Creates everything the two clusters need out of Keycloak: the realm, and the
# two OIDC clients that JWTs are minted for.
#
#   temporal-app          what people, the CLI and SDK clients authenticate as
#   temporal-replication  what each *cluster* authenticates as when it
#                         replicates to its peer
#
# Both get the one claim the receiving cluster's authorizer looks for:
#
#     permissions: ["temporal-system:admin"]
#
# "temporal-system" is the reserved namespace name that the default claim
# mapper reads as a cluster-wide scope (primitives.SystemLocalNamespace), and
# admin is the level AdminService APIs such as
# StreamWorkflowReplicationMessages require. Anything less and the peer accepts
# the connection, validates the signature, and then denies every replication
# call - which shows up as a silent replication stall rather than an auth error.
#
# Replication has no user behind it, so both clients use the client credentials
# grant and authenticate as their own service account.
#
# Run from the repo root once Keycloak is up:
#
#   docker compose up -d keycloak
#   ./scripts/setup-keycloak.sh
#
# The client secrets are written back into .env, which is where both compose
# files read them from.
#
# `temporal-app` is also what the Web UI signs users in with, so it gets the
# browser redirect flow and both UIs' callback URLs, plus a realm user to log
# in as (temporal / temporal).
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
ENV_FILE=${ENV_FILE:-$ROOT_DIR/.env}

KEYCLOAK_URL=${KEYCLOAK_URL:-http://localhost:9080}
KEYCLOAK_ADMIN=${KEYCLOAK_ADMIN:-admin}
KEYCLOAK_ADMIN_PASSWORD=${KEYCLOAK_ADMIN_PASSWORD:-admin}
REALM=${KEYCLOAK_REALM:-temporal}
APP_CLIENT_ID=${KEYCLOAK_CLIENT_ID:-temporal-app}
REPL_CLIENT_ID=${KEYCLOAK_REPLICATION_CLIENT_ID:-temporal-replication}

json() { python3 -c 'import json,sys; print(json.loads(sys.stdin.read())'"$1"')'; }

echo "Waiting for Keycloak at $KEYCLOAK_URL..."
for attempt in $(seq 1 60); do
  if curl -sf "$KEYCLOAK_URL/realms/master/.well-known/openid-configuration" >/dev/null 2>&1; then
    echo "  Keycloak is up"
    break
  fi
  if [ "$attempt" -eq 60 ]; then
    echo "  Keycloak did not become reachable. Is it running? (docker compose up -d keycloak)" >&2
    exit 1
  fi
  sleep 2
done

ADMIN_TOKEN=$(curl -sf -X POST \
  "$KEYCLOAK_URL/realms/master/protocol/openid-connect/token" \
  -d grant_type=password -d client_id=admin-cli \
  -d "username=$KEYCLOAK_ADMIN" -d "password=$KEYCLOAK_ADMIN_PASSWORD" \
  | json '["access_token"]')

# api <METHOD> <PATH-UNDER-/admin/realms> [curl args...]
api() {
  method=$1; path=$2; shift 2
  curl -s -X "$method" "$KEYCLOAK_URL/admin/realms$path" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" "$@"
}

# ---------------------------------------------------------------------------
# Realm
# ---------------------------------------------------------------------------
if curl -sf "$KEYCLOAK_URL/realms/$REALM/.well-known/openid-configuration" >/dev/null 2>&1; then
  echo "Realm '$REALM' already exists, reusing it"
else
  echo "Creating realm '$REALM'..."
  api POST "" -d "{\"realm\": \"$REALM\", \"enabled\": true}" >/dev/null
  curl -sf "$KEYCLOAK_URL/realms/$REALM/.well-known/openid-configuration" >/dev/null \
    || { echo "Realm creation failed" >&2; exit 1; }
fi

# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------
client_uuid() {
  api GET "/$REALM/clients?clientId=$1" \
    | python3 -c 'import json,sys; c=json.load(sys.stdin); print(c[0]["id"] if c else "")'
}

# ensure_client <clientId> <name> <directAccessGrants true|false>
ensure_client() {
  cid=$1; cname=$2; dag=$3
  uuid=$(client_uuid "$cid")
  if [ -n "$uuid" ]; then
    # stderr, not stdout: this function's stdout is the UUID itself
    echo "Client '$cid' already exists, reusing it" >&2
    printf '%s' "$uuid"
    return
  fi
  echo "Creating client '$cid'..." >&2
  # Confidential with a service account: a machine identity that can mint its
  # own token from client id + secret. standardFlow (browser redirect) stays
  # off - nothing here logs in interactively.
  api POST "/$REALM/clients" -d "{
    \"clientId\": \"$cid\",
    \"name\": \"$cname\",
    \"enabled\": true,
    \"protocol\": \"openid-connect\",
    \"publicClient\": false,
    \"serviceAccountsEnabled\": true,
    \"standardFlowEnabled\": false,
    \"implicitFlowEnabled\": false,
    \"directAccessGrantsEnabled\": $dag
  }" >/dev/null
  uuid=$(client_uuid "$cid")
  [ -n "$uuid" ] || { echo "Creating client '$cid' failed" >&2; exit 1; }
  printf '%s' "$uuid"
}

# add_permissions_mapper <client-uuid>
add_permissions_mapper() {
  uuid=$1
  mapper=temporal-system-admin
  existing=$(api GET "/$REALM/clients/$uuid/protocol-mappers/models" \
    | python3 -c "import json,sys; m=json.load(sys.stdin); print(next((x['id'] for x in m if x['name']=='$mapper'), ''))")
  if [ -n "$existing" ]; then
    api DELETE "/$REALM/clients/$uuid/protocol-mappers/models/$existing" >/dev/null
  fi
  # jsonType.label JSON makes Keycloak emit the value as a real JSON array.
  # The default claim mapper reads jwtClaims["permissions"].([]any); a plain
  # string claim fails that type assertion, is skipped silently, and the caller
  # ends up with no permissions at all.
  api POST "/$REALM/clients/$uuid/protocol-mappers/models" -d "{
    \"name\": \"$mapper\",
    \"protocol\": \"openid-connect\",
    \"protocolMapper\": \"oidc-hardcoded-claim-mapper\",
    \"config\": {
      \"claim.name\": \"permissions\",
      \"claim.value\": \"[\\\"temporal-system:admin\\\"]\",
      \"jsonType.label\": \"JSON\",
      \"access.token.claim\": \"true\",
      \"id.token.claim\": \"false\",
      \"userinfo.token.claim\": \"false\"
    }
  }" >/dev/null
}

# add_audience_mapper <client-uuid> <client-id>
#
# Puts the client's own id into the access token's `aud`. Keycloak's default
# audience is "account", and the Web UI verifies the token it forwards with an
# OIDC verifier that insists on seeing its own client id there -- without this
# the UI refuses every API call with
#   oidc: expected audience "temporal-app" got ["account"]
# even though the token is perfectly valid. The Temporal server itself does not
# check `aud` (it has no audience mapper configured), so this is additive.
add_audience_mapper() {
  uuid=$1; cid=$2
  mapper=temporal-audience
  existing=$(api GET "/$REALM/clients/$uuid/protocol-mappers/models" \
    | python3 -c "import json,sys; m=json.load(sys.stdin); print(next((x['id'] for x in m if x['name']=='$mapper'), ''))")
  if [ -n "$existing" ]; then
    api DELETE "/$REALM/clients/$uuid/protocol-mappers/models/$existing" >/dev/null
  fi
  api POST "/$REALM/clients/$uuid/protocol-mappers/models" -d "{
    \"name\": \"$mapper\",
    \"protocol\": \"openid-connect\",
    \"protocolMapper\": \"oidc-audience-mapper\",
    \"config\": {
      \"included.client.audience\": \"$cid\",
      \"access.token.claim\": \"true\",
      \"id.token.claim\": \"false\"
    }
  }" >/dev/null
}

APP_UUID=$(ensure_client "$APP_CLIENT_ID" "Temporal clients and operators" true)
add_permissions_mapper "$APP_UUID"
add_audience_mapper "$APP_UUID" "$APP_CLIENT_ID"
APP_SECRET=$(api GET "/$REALM/clients/$APP_UUID/client-secret" | json '["value"]')

REPL_UUID=$(ensure_client "$REPL_CLIENT_ID" "Temporal cross-cluster replication" false)
add_permissions_mapper "$REPL_UUID"
REPL_SECRET=$(api GET "/$REALM/clients/$REPL_UUID/client-secret" | json '["value"]')

# ---------------------------------------------------------------------------
# Optional: make temporal-app usable from the Web UI as well
# ---------------------------------------------------------------------------
echo "Enabling the browser redirect flow on '$APP_CLIENT_ID'..."
# The UI drives the authorization code flow, so unlike the pure machine
# identities above this client needs standardFlow and a registered callback.
api PUT "/$REALM/clients/$APP_UUID" -d "{
  \"clientId\": \"$APP_CLIENT_ID\",
  \"standardFlowEnabled\": true,
  \"redirectUris\": [
    \"http://localhost:8080/auth/sso/callback\",
    \"http://localhost:8081/auth/sso/callback\"
  ],
  \"webOrigins\": [\"http://localhost:8080\", \"http://localhost:8081\"]
}" >/dev/null

UI_USER=${KEYCLOAK_UI_USER:-temporal}
UI_PASSWORD=${KEYCLOAK_UI_PASSWORD:-temporal}
existing_user=$(api GET "/$REALM/users?username=$UI_USER&exact=true" \
  | python3 -c 'import json,sys; u=json.load(sys.stdin); print(u[0]["id"] if u else "")')
if [ -z "$existing_user" ]; then
  echo "Creating realm user '$UI_USER'..."
  api POST "/$REALM/users" -d "{
    \"username\": \"$UI_USER\",
    \"enabled\": true,
    \"emailVerified\": true,
    \"email\": \"$UI_USER@example.invalid\",
    \"firstName\": \"Temporal\",
    \"lastName\": \"Operator\",
    \"credentials\": [{\"type\": \"password\", \"value\": \"$UI_PASSWORD\", \"temporary\": false}]
  }" >/dev/null
else
  echo "Realm user '$UI_USER' already exists, reusing it"
fi
# The permissions mapper is hardcoded on the client, so this user's token
# carries temporal-system:admin too. Fine for a lab; in anything real the
# claim should come from the user's own roles.

# ---------------------------------------------------------------------------
# Verify each client really mints a token with the claim the server needs
# ---------------------------------------------------------------------------
verify() {
  cid=$1; secret=$2
  token=$(curl -sf -X POST \
    "$KEYCLOAK_URL/realms/$REALM/protocol/openid-connect/token" \
    -d grant_type=client_credentials \
    -d "client_id=$cid" -d "client_secret=$secret" \
    | json '["access_token"]')
  python3 - "$cid" "$token" <<'PY'
import base64, json, sys
cid, token = sys.argv[1], sys.argv[2]
payload = token.split(".")[1]
payload += "=" * (-len(payload) % 4)
claims = json.loads(base64.urlsafe_b64decode(payload))
print(f"  {cid}: sub={claims.get('sub')} permissions={claims.get('permissions')} aud={claims.get('aud')}")
if claims.get("permissions") != ["temporal-system:admin"]:
    sys.exit(f"  {cid}: permissions claim is wrong; Temporal will deny its calls")
PY
}

echo
echo "Verifying minted tokens..."
verify "$APP_CLIENT_ID" "$APP_SECRET"
verify "$REPL_CLIENT_ID" "$REPL_SECRET"

# ---------------------------------------------------------------------------
# Write the secrets into .env, where both compose files read them
# ---------------------------------------------------------------------------
set_env() {
  key=$1; value=$2
  touch "$ENV_FILE"
  if grep -q "^$key=" "$ENV_FILE"; then
    python3 - "$ENV_FILE" "$key" "$value" <<'PY'
import sys
path, key, value = sys.argv[1], sys.argv[2], sys.argv[3]
lines = open(path).read().splitlines()
out = [f"{key}={value}" if l.startswith(key + "=") else l for l in lines]
open(path, "w").write("\n".join(out) + "\n")
PY
  else
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
  echo "  $key"
}

echo
echo "Writing secrets to $ENV_FILE..."
set_env KEYCLOAK_CLIENT_SECRET "$APP_SECRET"
set_env KEYCLOAK_REPLICATION_SECRET "$REPL_SECRET"

echo
echo "Keycloak is ready."
echo "  JWKS the clusters verify tokens against:"
echo "    $KEYCLOAK_URL/realms/$REALM/protocol/openid-connect/certs"
echo "  Web UI sign-in (http://localhost:8080 and :8081):"
echo "    $UI_USER / $UI_PASSWORD"
