#!/usr/bin/env bash
# Mint a one-time password-reset link for a principal, handed over out of band.
set -euo pipefail

cd "$(dirname "$0")/.."

# The control container: EP_CONTROL_CONTAINER, else the container labelled
# app=emuplane (the overlay names it), else the compose default name.
container=$(sed -n 's/^EP_CONTROL_CONTAINER=//p' .env)
if [ -z "$container" ]; then
  container=$(podman ps -a --filter label=app=emuplane --format '{{.Names}}' | head -n 1)
fi
container=${container:-emuplane}

if ! podman container exists "$container"; then
  echo "the control container ($container) does not exist: ./scripts/up.sh first" >&2
  exit 1
fi

podman exec "$container" python /app/password.py "$1" --link
