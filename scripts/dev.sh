#!/usr/bin/env bash
# The inner dev loop, without rebuilding the image.
#
#   ./scripts/dev.sh up     # start with the dev overlay (mounts the source)
#   ./scripts/dev.sh web    # rebuild the console on the host (~1s), then refresh
#   ./scripts/dev.sh api    # restart the control after a Python change (~2s)
#   ./scripts/dev.sh all    # console build, then the restart
#
# Why this is faster than `up.sh --build`: the image build re-runs `COPY web/`,
# `npm run build` inside the container and commits a layer — ~30s here. Vite on
# the host builds the same output in under a second, and the container reads
# /app/static per request, so the browser sees it on the next refresh. A Python
# change needs only a restart, which re-imports the mounted files.
#
# `./scripts/up.sh --build` stays the release path; this is not.
set -euo pipefail

cd "$(dirname "$0")/.."

port=$(sed -n 's/^EP_UI_PORT=//p' .env 2>/dev/null)
port=${port:-4570}

web() {
  if [ ! -d web/node_modules ]; then
    echo "web/node_modules is missing: npm --prefix web ci first" >&2
    exit 1
  fi
  local started
  started=$(date +%s)
  npm --prefix web run build >/dev/null
  printf 'console built in %ss — refresh the browser\n' "$(( $(date +%s) - started ))"
}

api() {
  # Discovery lives here, so `web` never needs podman and works from a sandbox or a shell without it.
  local container
  container=$(sed -n 's/^EP_CONTROL_CONTAINER=//p' .env 2>/dev/null)
  if [ -z "$container" ]; then
    container=$(podman ps -a --filter label=app=emuplane --format '{{.Names}}' | head -n 1)
  fi
  container=${container:-emuplane}
  podman restart "$container" >/dev/null
  for _ in $(seq 1 30); do
    if curl -fsS -m 2 -o /dev/null "http://127.0.0.1:${port}/health"; then
      echo "control restarted and healthy on 127.0.0.1:${port}"
      return 0
    fi
    sleep 1
  done
  echo "control did not come back: podman logs $container" >&2
  return 1
}

case "${1:-}" in
  up)
    EP_DEV=1 ./scripts/up.sh
    ;;
  web) web ;;
  api) api ;;
  all) web; api ;;
  *)
    sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'
    exit 2
    ;;
esac
