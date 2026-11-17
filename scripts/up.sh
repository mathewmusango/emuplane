#!/usr/bin/env bash
# Start Emuplane: gateway, console, accounts; the backend must be reachable first, or every request errors.
set -euo pipefail

cd "$(dirname "$0")/.."

# Flags: `--build` rebuilds for a maintainer, `--pull` refreshes a published image, `--dev` mounts the source.
build=0
pull=0
dev=${EP_DEV:-0}
for argument in "$@"; do
  case "$argument" in
    --build) build=1 ;;
    --pull) pull=1 ;;
    --dev) dev=1 ;;
    *) echo "unknown option: $argument (try --build, --pull or --dev)" >&2; exit 2 ;;
  esac
done
if [ "$build" = "1" ]; then
  ./scripts/build.sh
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "created .env from .env.example"
fi
chmod 600 .env

# No seeded account or credential: a fresh control offers sign-up only, and ./scripts/token.sh mints the token.

# EP_BACKEND_URL in .env is the source of truth; empty means derive it from a container name and port.
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

# A local container named in the URL must be running: fail early with a useful sentence. A remote URL skips this.
host=${node_url#*://}
host=${host%%/*}
host=${host%%:*}
if podman container exists "$host" 2>/dev/null; then
  if [ "$(podman inspect --format '{{.State.Running}}' "$host" 2>/dev/null)" != "true" ]; then
    echo "the backend ($host) is not running: start it first" >&2
    exit 1
  fi
fi

# docker-compose.yml is generic; an untracked overlay (compose.lab.yml, or EP_OVERLAY) adds names, routes, network, mounts and the project name, so -p is explicit.
overlay=$(sed -n 's/^EP_OVERLAY=//p' .env)
overlay=${overlay:-compose.lab.yml}
project=$(sed -n 's/^EP_PROJECT_NAME=//p' .env)
if [ -z "$project" ] && [ -f "$overlay" ]; then
  project=$(sed -n 's/^name: *//p' "$overlay" | head -n 1)
fi
project=${project:-emuplane}

compose=(podman-compose -p "$project" -f docker-compose.yml)
if [ -n "$overlay" ] && [ -f "$overlay" ]; then
  compose+=(-f "$overlay")
fi

# `--dev` (or EP_DEV=1) mounts the console and the control source: a change costs a vite build or a restart.
if [ "$dev" = "1" ]; then
  # Generated and ignored: the module list is read from disk, so a new control/*.py needs no edit here.
  {
    echo "services:"
    echo "  emuplane:"
    echo "    volumes:"
    if [ -d web/dist ]; then
      echo "      - ./web/dist:/app/static:ro,Z"
    fi
    for module in control/*.py; do
      echo "      - ./${module}:/app/${module##*/}:ro,Z"
    done
  } > compose.dev.yml
  compose+=(-f compose.dev.yml)
  echo "dev overlay: console and control source are mounted, not baked"
fi

# An end user pulls the published image; only a maintainer builds one (`--build`).
image=""
if [ -f "$overlay" ]; then
  image=$(sed -n 's/^[[:space:]]*image:[[:space:]]*//p' "$overlay" | head -n 1)
fi
if [ -z "$image" ]; then
  image=$(sed -n 's/^[[:space:]]*image:[[:space:]]*//p' docker-compose.yml | head -n 1)
fi
image=$(printf '%s' "$image" | tr -d '"')
if [ "$build" = "0" ]; then
  if [ "$pull" = "1" ] || ! podman image exists "$image"; then
    echo "pulling $image"
    "${compose[@]}" pull
  fi
fi

# The overlay declares the network it joins, so read the name there; EP_NETWORK overrides, and up.sh creates it if missing.
network=$(sed -n 's/^EP_NETWORK=//p' .env)
if [ -z "$network" ] && [ -f "$overlay" ]; then
  network=$(awk '/^networks:/{block=1; next}
    block && /^[^[:space:]]/ {block=0}
    block && /^[[:space:]]+[A-Za-z0-9_.-]+:/ {line=$0; gsub(/^[[:space:]]+/, "", line); sub(/:.*/, "", line); print line; exit}' "$overlay")
fi
if [ -n "$network" ] && ! podman network exists "$network"; then
  podman network create "$network"
fi

# Provision the control's own DynamoDB tables: idempotent, and the control refuses to serve until they exist.
echo "applying the control stack (bootstrap/apply.py)"
"${compose[@]}" run --rm --no-deps bootstrap

"${compose[@]}" up -d --force-recreate

ui_port=$(sed -n 's/^EP_PORT=//p' .env)
ui_port=${ui_port:-4570}
gateway_port=$(sed -n 's/^EP_GATEWAY_PORT=//p' .env)
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
