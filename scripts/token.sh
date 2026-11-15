#!/usr/bin/env bash
# Mint or inspect the control's API bearer token.
#
# The token is a credential, so it is not stored in .env and not written to the
# container log: it lives in the settings store as a SHA-256 hash, and the raw
# value is printed here exactly once. Rotating invalidates the previous token
# immediately.
#
#   ./scripts/token.sh            # rotate: prints the new token once
#   ./scripts/token.sh --status   # is one set, and when was it made
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

podman exec "$container" python /app/api_token.py "$@"
