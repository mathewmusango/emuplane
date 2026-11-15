#!/usr/bin/env bash
# Start the control plane: gateway, console, accounts.
#
# The node this control fronts (MiniStack, Floci, any AWS-compatible emulator) is
# a separate service and a separate repository. This script refuses to start
# until it is running, because a gateway with no node answers every request with
# an error.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  cp .env.example .env
  echo "created .env from .env.example"
fi
chmod 600 .env

# There is no seeded account and no seeded credential: a fresh control only
# offers sign-up, and the API bearer token is minted on demand by
# ./scripts/token.sh (stored hashed, printed once — never kept in .env).

require() {
  value=$(sed -n "s/^$1=//p" .env)
  if [ -z "$value" ]; then
    echo "missing $1 in .env" >&2
    exit 1
  fi
  printf '%s' "$value"
}

# The node this control fronts: its container name, a label to discover it by, or
# an explicit URL. Nothing here names a particular emulator — MiniStack, Floci or
# another LocalStack-compatible API server all work.
node_url=$(sed -n 's/^MC_NODE_URL=//p' .env)
node_container=$(sed -n 's/^MC_NODE_CONTAINER=//p' .env)
node_label=$(sed -n 's/^MC_NODE_LABEL=//p' .env)
if [ -z "$node_container" ] && [ -n "$node_label" ]; then
  node_container=$(podman ps -a --filter "label=$node_label" --format '{{.Names}}' | head -n 1)
fi
node_port=$(sed -n 's/^MC_NODE_PORT=//p' .env)
node_port=${node_port:-4566}
if [ -z "$node_url" ]; then
  if [ -z "$node_container" ]; then
    echo "name the node in .env: MC_NODE_CONTAINER, MC_NODE_LABEL or MC_NODE_URL" >&2
    exit 1
  fi
  node_url="http://${node_container}:${node_port}"
fi
# compose reads this; .env never has to carry the derived value.
export MC_NODE_URL="$node_url"
export MC_NODE_CONTAINER="$node_container"

if [ -n "$node_container" ]; then
  if ! podman container exists "$node_container"; then
    echo "the node is not created: start it first ($node_container)" >&2
    exit 1
  fi
  if [ "$(podman inspect --format '{{.State.Running}}' "$node_container" 2>/dev/null)" != "true" ]; then
    echo "the node ($node_container) is not running: start it first" >&2
    exit 1
  fi
fi

# docker-compose.yml is the generic definition; an untracked overlay (compose.yml
# by default, or whatever MC_OVERLAY names) may add container names, routes, an
# external network and extra mounts. The overlay also carries the compose project
# name (`name:`), which is read from it — MC_PROJECT_NAME still overrides.
# -p is explicit because podman-compose resolves the project name from the first
# file and would otherwise miss the containers the overlay named.
overlay=$(sed -n 's/^MC_OVERLAY=//p' .env)
overlay=${overlay:-compose.yml}
project=$(sed -n 's/^MC_PROJECT_NAME=//p' .env)
if [ -z "$project" ] && [ -f "$overlay" ]; then
  project=$(sed -n 's/^name: *//p' "$overlay" | head -n 1)
fi
project=${project:-ministack-control}

compose=(podman-compose -p "$project" -f docker-compose.yml)
if [ -n "$overlay" ] && [ -f "$overlay" ]; then
  compose+=(-f "$overlay")
fi

# The overlay usually joins a network the emulator is already on; MC_NETWORK names
# it, and up.sh creates it when it is missing.
network=$(sed -n 's/^MC_NETWORK=//p' .env)
if [ -n "$network" ] && ! podman network exists "$network"; then
  podman network create "$network"
fi

# First setup, and every start after it: provision the control's own substrate.
# The stack owns the ten DynamoDB tables the control stores itself in; the job is
# idempotent and the control refuses to serve until the tables exist.
echo "applying the control stack (bootstrap/apply.py)"
"${compose[@]}" run --rm --no-deps bootstrap

"${compose[@]}" up -d --force-recreate

ui_port=$(sed -n 's/^MC_UI_PORT=//p' .env)
ui_port=${ui_port:-4570}
gateway_port=$(sed -n 's/^MC_GATEWAY_PORT=//p' .env)
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
printf '  node gateway 127.0.0.1:%s  (use an access key from the console)\n' "$gateway_port"
printf '\nThe node (%s) is reached over the compose network, never published.\n' "$node_url"
