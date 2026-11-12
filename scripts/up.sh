#!/usr/bin/env bash
# Start the MiniStack control plane: gateway, console, accounts.
#
# The emulator is a separate service and a separate repository. This script
# refuses to start until it is running, because a gateway with no emulator
# answers every request with an error.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  cp .env.example .env
  echo "created .env from .env.example"
fi
chmod 600 .env

# First-run secrets are seeded into .env itself, so they survive a data wipe and
# the container never needs to write to the host. An existing value always wins.
python3 - <<'PY'
from pathlib import Path
import secrets
import sys

path = Path(".env")
lines = path.read_text().splitlines()

def value_of(key):
    for line in lines:
        if line.startswith(key + "="):
            return line.partition("=")[2].strip()
    return ""

generated = []
for key, factory in (
    ("MC_ADMIN_TOKEN", lambda: secrets.token_hex(24)),
    ("MC_ADMIN_PASSWORD", lambda: secrets.token_urlsafe(18)),
):
    if not value_of(key):
        generated.append((key, factory()))

if not generated:
    sys.exit(0)

keys = dict(generated)
out, replaced = [], set()
for line in lines:
    key = line.partition("=")[0].strip()
    if key in keys:
        out.append(f"{key}={keys[key]}")
        replaced.add(key)
    else:
        out.append(line)
for key, value in generated:
    if key not in replaced:
        out.append(f"{key}={value}")

path.write_text("\n".join(out) + "\n")
path.chmod(0o600)
print("seeded into .env: " + ", ".join(key for key, _ in generated))
PY

require() {
  value=$(sed -n "s/^$1=//p" .env)
  if [ -z "$value" ]; then
    echo "missing $1 in .env" >&2
    exit 1
  fi
  printf '%s' "$value"
}

data_dir=$(require MC_DATA_DIR)
install -d -m 0755 "$data_dir"

# The emulator is a separate service. Its container name is a lab detail, so it
# comes from .env (default: the compose service name).
emulator=$(sed -n 's/^MC_EMULATOR_CONTAINER=//p' .env)
emulator=${emulator:-ministack}

if ! podman container exists "$emulator"; then
  echo "the emulator is not created: start it first" >&2
  echo "  cd ../ministack && ./scripts/up.sh" >&2
  exit 1
fi
if [ "$(podman inspect --format '{{.State.Running}}' "$emulator" 2>/dev/null)" != "true" ]; then
  echo "the emulator ($emulator) is not running: start it first" >&2
  echo "  cd ../ministack && ./scripts/up.sh" >&2
  exit 1
fi

# The project name prefixes the containers' compose labels; the default matches
# the generic compose.yml.
project=$(sed -n 's/^MC_PROJECT_NAME=//p' .env)
project=${project:-ministack-control}

# compose.yml is the generic definition; an untracked overlay of the same name
# (compose.<site>.yml, picked up from MC_OVERLAY) may add container names, routes,
# an external network and extra mounts. -p is explicit because podman-compose
# resolves the project name from the first file and would otherwise miss the
# containers the overlay named.
compose=(podman-compose -p "$project" -f compose.yml)
overlay=$(sed -n 's/^MC_OVERLAY=//p' .env)
if [ -n "$overlay" ] && [ -f "$overlay" ]; then
  compose+=(-f "$overlay")
fi

# The overlay usually joins a network the emulator is already on; MC_NETWORK names
# it, and up.sh creates it when it is missing.
network=$(sed -n 's/^MC_NETWORK=//p' .env)
if [ -n "$network" ] && ! podman network exists "$network"; then
  podman network create "$network"
fi

"${compose[@]}" up -d --force-recreate

ui_port=$(require MC_UI_PORT)
gateway_port=$(require MC_GATEWAY_PORT)

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
printf '  emulator gateway 127.0.0.1:%s  (use an access key from the console)\n' "$gateway_port"
printf '\nThe emulator (%s) is reached over the compose network, never published.\n' "$emulator"
