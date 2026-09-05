# Temporal server with the replication TokenProvider compiled in.
#
# temporal.WithTokenProvider is a Go server option rather than a config key, so
# securing replication with a JWT means shipping a server binary of our own.
# main.go is upstream cmd/server/main.go plus that one option; everything else
# about the server is stock.

ARG GO_VERSION=1.26
FROM golang:${GO_VERSION} AS builder

WORKDIR /src

# Dependencies first, so editing main.go or tokenprovider.go does not re-download
# the (very large) Temporal server module tree.
COPY go.mod go.sum ./
RUN go mod download

COPY main.go tokenprovider.go ./
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/temporal-server .

FROM debian:bookworm-slim

RUN useradd --uid 1000 --create-home --shell /bin/bash temporal

# The trust store comes from the builder image rather than from apt. The token
# provider needs it to reach an HTTPS token endpoint - the local Keycloak is
# plain HTTP, but a real deployment's will not be - and lifting the bundle out
# of the builder keeps this stage from needing a package mirror at build time.
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
COPY --from=builder /out/temporal-server /usr/local/bin/temporal-server
COPY entrypoint.sh /etc/temporal/entrypoint.sh

USER temporal
WORKDIR /home/temporal

# TEMPORAL_SERVER_CONFIG_FILE_PATH and TEMPORAL_SERVICES are read straight off
# the environment by the server CLI, so the compose files keep the same contract
# they had with the official image.
ENTRYPOINT ["/etc/temporal/entrypoint.sh"]
CMD ["start"]
