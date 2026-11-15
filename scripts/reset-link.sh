#!/usr/bin/env bash
# Mint a one-time password-reset link for a principal.
#
# There is no mail transport on this server, so the link is handed over out of
# band: run this, send the URL to the person, and they choose their own password
# on `/reset`. The token is stored only as a digest, it expires after
# EP_RESET_SECONDS (30 min by default), and it stops working once used.
#
#   ./scripts/reset-link.sh <username>
#
# If the person cannot be reached at all, `./scripts/password.sh <username>` sets
# the password outright instead.
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
