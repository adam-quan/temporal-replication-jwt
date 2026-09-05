#!/bin/sh
#
# Mints a Keycloak access token with the client credentials grant and prints it.
#
# Sourced by the other scripts, and useful by hand inside the admin-tools
# containers, where the Temporal CLI picks the token up from the environment:
#
#   docker compose exec temporal-admin-tools sh
#   export TEMPORAL_GRPC_META_AUTHORIZATION="Bearer $(/scripts/token.sh)"
#   temporal operator cluster list
#
# Prints nothing and exits non-zero on failure, so callers can retry while
# Keycloak is still starting. Only wget and sed are available in the
# admin-tools image, hence no curl or jq.
KEYCLOAK_URL=${KEYCLOAK_URL:-http://keycloak:9080}
KEYCLOAK_REALM=${KEYCLOAK_REALM:-temporal}
KEYCLOAK_CLIENT_ID=${KEYCLOAK_CLIENT_ID:-temporal-app}

if [ -z "${KEYCLOAK_CLIENT_SECRET:-}" ]; then
  echo "KEYCLOAK_CLIENT_SECRET is not set (see .env)" >&2
  exit 1
fi

response=$(wget -q -O - \
  --header='Content-Type: application/x-www-form-urlencoded' \
  --post-data="grant_type=client_credentials&client_id=$KEYCLOAK_CLIENT_ID&client_secret=$KEYCLOAK_CLIENT_SECRET" \
  "$KEYCLOAK_URL/realms/$KEYCLOAK_REALM/protocol/openid-connect/token" 2>/dev/null) || exit 1

token=$(printf '%s' "$response" | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')
[ -n "$token" ] || exit 1
printf '%s' "$token"
