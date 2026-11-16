#!/usr/bin/env bash
# Reset a principal's password from the host, with no mail transport, and revoke every session it held.
set -euo pipefail

cd "$(dirname "$0")/.."

# The control container: EP_CONTROL_CONTAINER, else the app=emuplane container, else the compose default name.
container=$(sed -n 's/^EP_CONTROL_CONTAINER=//p' .env)
if [ -z "$container" ]; then
  container=$(podman ps -a --filter label=app=emuplane --format '{{.Names}}' | head -n 1)
fi
container=${container:-emuplane}

if ! podman container exists "$container"; then
  echo "the control container ($container) does not exist: ./scripts/up.sh first" >&2
  exit 1
fi

podman exec "$container" python /app/password.py "$@"
