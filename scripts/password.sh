#!/usr/bin/env bash
# Reset a principal's password when nobody can sign in as it.
#
# This deployment has no mail transport, so there is no emailed reset link: the
# platform owner issues the new password from the host. Every session the user
# holds is revoked at the same time.
#
#   ./scripts/password.sh <username>                     # generate, print once
#   ./scripts/password.sh <username> --password VALUE    # set a chosen one
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

podman exec "$container" python /app/password.py "$@"
