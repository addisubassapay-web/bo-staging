#!/bin/bash
# Self-healing redis-server launcher. Emergent pods lose apt-installed
# packages across restarts, so we reinstall on the fly when the binary is
# missing. Idempotent — the second-and-later start is instant.
set -e
if [ ! -x /usr/bin/redis-server ]; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq 2>/dev/null || true
    apt-get install -y --no-install-recommends redis-server >/dev/null 2>&1 || true
fi
exec /usr/bin/redis-server --port 6379 --dir /tmp --save "" --appendonly no
