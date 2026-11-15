#!/usr/bin/env bash
# Start Emuplane: gateway, console, accounts.
#
# The backend is a separate service and a separate repository. This script refuses
# to start until it is reachable, because a gateway with no backend answers every
# request with an error.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  cp .env.example .env
  echo "created .env from .env.example"
fi
chmod 600 .env

# There is no seeded account and no seeded credential: a fresh control only offers
# sign-up, and the API bearer token is minted on demand by ./scripts/token.sh
# (stored hashed, printed once — never kept in .env).

# The backend connection string: EP_BACKEND_URL in .env is the source of truth.
# With it empty, the URL is derived from a container name and the default port, so
# a compose-only setup still works.
node_url=$(sed -n 's/^EP_BACKEND_URL=//p' .env)
if [ -z "$node_url" ]; then
  node_container=$(sed -n 's/^EP_BACKEND_CONTAINER=//p' .env)
  node_port=$(sed -n 's/^EP_BACKEND_PORT=//p' .env)
  node_port=${node_port:-4566}
  if [ -z "$node_container" ]; then
    echo "set EP_BACKEND_URL in .env — the backend's connection string" >&2
    exit 1
  fi
  node_url="http://${node_container}:${node_port}"
fi
export EP_BACKEND_URL="$node_url"

# When the URL names a local container, fail early with a useful sentence rather
# than letting the control report an unreachable backend. A remote URL skips this.
host=${node_url#*://}
host=${host%%/*}
host=${host%%:*}
if podman container exists "$host" 2>/dev/null; then
  if [ "$(podman inspect --format '{{.State.Running}}' "$host" 2>/dev/null)" != "true" ]; then
    echo "the backend ($host) is not running: start it first" >&2
    exit 1
  fi
fi

# docker-compose.yml is the generic definition; an untracked overlay (compose.yml
# by default, or whatever EP_OVERLAY names) may add container names, routes, an
# external network and extra mounts. The overlay also carries the compose project
# name (`name:`), which is read from it — EP_PROJECT_NAME still overrides.
# -p is explicit because podman-compose resolves the project name from the first
# file and would otherwise miss the containers the overlay named.
overlay=$(sed -n 's/^EP_OVERLAY=//p' .env)
overlay=${overlay:-compose.yml}
project=$(sed -n 's/^EP_PROJECT_NAME=//p' .env)
if [ -z "$project" ] && [ -f "$overlay" ]; then
  project=$(sed -n 's/^name: *//p' "$overlay" | head -n 1)
fi
project=${project:-emuplane}

compose=(podman-compose -p "$project" -f docker-compose.yml)
if [ -n "$overlay" ] && [ -f "$overlay" ]; then
  compose+=(-f "$overlay")
fi

# The overlay joins a network the backend is already on. It is declared there
# (`networks:`), so the name is read from the overlay rather than configured twice;
# EP_NETWORK still overrides, and up.sh creates the network when it is missing.
network=$(sed -n 's/^EP_NETWORK=//p' .env)
if [ -z "$network" ] && [ -f "$overlay" ]; then
  network=$(awk '/^networks:/{block=1; next}
    block && /^[^[:space:]]/ {block=0}
    block && /^[[:space:]]+[A-Za-z0-9_.-]+:/ {line=$0; gsub(/^[[:space:]]+/, "", line); sub(/:.*/, "", line); print line; exit}' "$overlay")
fi
if [ -n "$network" ] && ! podman network exists "$network"; then
  podman network create "$network"
fi

# First setup, and every start after it: provision the control's own substrate.
# The stack owns the ten DynamoDB tables the control stores itself in; the job is
# idempotent and the control refuses to serve until the tables exist.
echo "applying the control stack (bootstrap/apply.py)"
"${compose[@]}" run --rm --no-deps bootstrap

"${compose[@]}" up -d --force-recreate

ui_port=$(sed -n 's/^EP_UI_PORT=//p' .env)
ui_port=${ui_port:-4570}
gateway_port=$(sed -n 's/^EP_PUBLISHED_GATEWAY_PORT=//p' .env)
gateway_port=${gateway_port:-4571}

for _ in $(seq 1 60); do
  if curl -fsS -m 2 -o /dev/null "http://127.0.0.1:${ui_port}/health"; then
    printf 'control ready on 127.0.0.1:%s/health\n' "$ui_port"
    break
  fi
  sleep 2
done

printf '\nendpoints (only these are published):\n'
printf '  dashboard   http://127.0.0.1:%s/  (sign in required)\n' "$ui_port"
printf '  control API http://127.0.0.1:%s/api/%s/\n' "$ui_port" v1
printf '  backend gateway 127.0.0.1:%s  (use an access key from the console)\n' "$gateway_port"
printf '\nThe backend (%s) is reached over the compose network, never published.\n' "$node_url"
