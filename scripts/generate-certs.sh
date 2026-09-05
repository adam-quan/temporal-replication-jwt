#!/usr/bin/env bash
#
# Generates the self-signed PKI both Temporal clusters serve TLS with.
#
#   certs/ca/ca.pem                  root CA, trusted by both clusters
#   certs/<cluster>/internode.pem    internode + internal-frontend identity
#   certs/<cluster>/frontend.pem     public frontend identity
#
# TLS is not optional here. The replication credential is a bearer token, and
# the server attaches it through gRPC PerRPCCredentials whose
# RequireTransportSecurity() returns true (RFC 9700) - so a plaintext
# cross-cluster dial cannot carry a token at all. TLS is what makes the JWT
# path possible; the JWT is what identifies the caller.
#
# Both leaf certificates are serverAuth only. No client certificates are
# issued, because no listener asks for one: requireClientAuth is off
# everywhere and callers are identified by their Keycloak JWT instead.
#
# One CA signs both clusters, so each trusts the other's certificate. For
# separate per-cluster CAs, run this twice with different CA_DIR values and
# list both CA files under `rootCaFiles` in each cluster's config.yaml.
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
CERTS_DIR=${CERTS_DIR:-$ROOT_DIR/certs}
CA_DIR=$CERTS_DIR/ca
DAYS=${CERT_DAYS:-3650}
KEY_BITS=${CERT_KEY_BITS:-2048}

# Hostnames each cluster is reachable at. These must match the `serverName`
# fields in the corresponding config.yaml, because that pin is what host
# verification checks.
A_INTERNAL_NAME=${CLUSTER_A_INTERNAL_NAME:-temporal-a.internal}
B_INTERNAL_NAME=${CLUSTER_B_INTERNAL_NAME:-temporal-b.internal}
A_HOST=${CLUSTER_A_HOST:-temporal}
B_HOST=${CLUSTER_B_HOST:-temporal-b}

mkdir -p "$CA_DIR"

# Self-signed root, reused on re-runs so existing leaf certs stay valid.
create_ca() {
  if [ -f "$CA_DIR/ca.pem" ] && [ -f "$CA_DIR/ca.key" ]; then
    echo "CA already exists at $CA_DIR/ca.pem, reusing it"
    return
  fi
  echo "Generating root CA..."
  openssl req -x509 -newkey "rsa:$KEY_BITS" -nodes \
    -keyout "$CA_DIR/ca.key" -out "$CA_DIR/ca.pem" -days "$DAYS" \
    -subj "/O=Temporal XDC Lab/CN=Temporal XDC Root CA" \
    -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
    -addext "keyUsage=critical,keyCertSign,cRLSign" 2>/dev/null
}

# issue <out_dir> <name> <common_name> <san_list>
issue() {
  out_dir=$1; name=$2; cn=$3; sans=$4
  mkdir -p "$out_dir"
  echo "  issuing $name.pem (CN=$cn)"

  ext_file=$(mktemp)
  cat > "$ext_file" <<EXT
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=$sans
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid,issuer
EXT

  openssl req -newkey "rsa:$KEY_BITS" -nodes \
    -keyout "$out_dir/$name.key" -out "$out_dir/$name.csr" \
    -subj "/O=Temporal XDC Lab/CN=$cn" 2>/dev/null

  openssl x509 -req -in "$out_dir/$name.csr" \
    -CA "$CA_DIR/ca.pem" -CAkey "$CA_DIR/ca.key" -CAcreateserial \
    -out "$out_dir/$name.pem" -days "$DAYS" -extfile "$ext_file" 2>/dev/null

  rm -f "$out_dir/$name.csr" "$ext_file"
}

# issue_cluster <dir_name> <internal_name> <container_host>
issue_cluster() {
  dir=$CERTS_DIR/$1; internal_name=$2; host=$3
  echo "Generating certificates for $1..."

  # Served on the internode and internal-frontend listeners. Services find each
  # other by container IP through the membership ring, so the config pins
  # serverName to this name rather than verifying against a dialed address.
  issue "$dir" internode "$internal_name" \
    "DNS:$internal_name,DNS:$host,DNS:localhost,IP:127.0.0.1"

  # Served on the public frontend: to the CLI, the Web UI, SDK clients, and to
  # the peer cluster's replication stream alike.
  issue "$dir" frontend "$host" \
    "DNS:$host,DNS:$internal_name,DNS:localhost,IP:127.0.0.1"
}

create_ca
issue_cluster cluster-a "$A_INTERNAL_NAME" "$A_HOST"
issue_cluster cluster-b "$B_INTERNAL_NAME" "$B_HOST"

# The server runs as uid 1000 inside the container and reads these through a
# read-only bind mount, so the private keys have to be world readable. Fine for
# a local lab, never do this with certificates that protect anything.
chmod 644 "$CA_DIR"/*.key "$CERTS_DIR"/cluster-*/*.key

echo
echo "Done. Certificates written to $CERTS_DIR"
openssl x509 -in "$CA_DIR/ca.pem" -noout -subject -dates
