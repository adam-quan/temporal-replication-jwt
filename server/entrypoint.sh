#!/bin/sh
# Mirrors the entrypoint of the official temporalio/server image.
#
# The config files in config/ read `bindOnIP` from BIND_ON_IP and default it to
# 127.0.0.1. That default is only right for a single-process local run: a
# service bound to container loopback is unreachable both from a published host
# port (Docker DNATs to the container's own IP, not to its loopback) and from
# the peer cluster. So resolve the container's address and bind on that, which
# is what the official image does.
#
# If BIND_ON_IP is explicitly set to a wildcard, membership can no longer infer
# a routable address to advertise to the other services, so publish one
# explicitly. ringpop requires broadcastAddress to parse as a literal IP
# (net.ParseIP), which is why a container name will not do here.
set -eu

: "${BIND_ON_IP:=$(getent hosts "$(hostname)" | awk '{print $1;}')}"
export BIND_ON_IP

if [ "${BIND_ON_IP}" = "0.0.0.0" ] || [ "${BIND_ON_IP}" = "::0" ]; then
    : "${TEMPORAL_BROADCAST_ADDRESS:=$(getent hosts "$(hostname)" | awk '{print $1;}')}"
    export TEMPORAL_BROADCAST_ADDRESS
fi

exec /usr/local/bin/temporal-server "$@"
