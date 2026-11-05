#!/usr/bin/env bash
# Start the MiniStack control plane: gateway, console, accounts.
#
# The emulator is a separate service (`services/ministack`). This script
# refuses to start until it is running, because a gateway with no emulator
# answers every request with an error.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "missing .env: cp .env.example .env and fill it in" >&2
  exit 1
fi

data_dir=$(sed -n 's/^MINISTACK_CONTROL_DATA_DIR=//p' .env)
data_dir=${data_dir:-/srv/myinfra/containers/ministack/data/control}
if [ ! -d "$data_dir" ]; then
  echo "missing data directory: $data_dir" >&2
  echo "create it once: install -d -m 0755 $data_dir" >&2
  exit 1
fi

if ! podman container exists core-ministack; then
  echo "the emulator is not created: start it first" >&2
  echo "  cd ../ministack && ./scripts/up.sh" >&2
  exit 1
fi
if [ "$(podman inspect --format '{{.State.Running}}' core-ministack 2>/dev/null)" != "true" ]; then
  echo "the emulator (core-ministack) is not running: start it first" >&2
  echo "  cd ../ministack && ./scripts/up.sh" >&2
  exit 1
fi

if ! podman network exists net-services; then
  podman network create net-services
fi

podman-compose build
podman-compose up -d

ui_port=$(sed -n 's/^MINISTACK_UI_PORT=//p' .env)
ui_port=${ui_port:-4570}
gateway_port=$(sed -n 's/^MINISTACK_GATEWAY_PORT=//p' .env)
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
printf '  AWS gateway 127.0.0.1:%s  (use an access key from the console)\n' "$gateway_port"
printf '\nThe emulator (core-ministack) is internal to net-services.\n'
