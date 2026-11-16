#!/usr/bin/env bash
# Build the Emuplane image, reusing every cache podman can give us.
#
#   ./scripts/build.sh              # incremental, cached
#   ./scripts/build.sh --no-cache   # ignore the layer cache (base-image bump)
#
# The Dockerfile is built to be cheap to rebuild:
#
#   - `npm ci` sits before `COPY web/`, so a source change never reinstalls;
#   - npm's package cache and Vite's transform cache are `--mount=type=cache`,
#     so neither is downloaded/redone but neither lands in a layer;
#   - `web/dist` is copied from the build stage, so the runtime image carries
#     no node_modules, no npm cache and no toolchain.
#
# `--layers` is explicit because it is the whole point: podman caches each
# instruction, and a no-change rebuild ends in a few seconds.
set -euo pipefail

cd "$(dirname "$0")/.."

image=${EP_IMAGE:-}
if [ -z "$image" ]; then
  image=$(sed -n 's/^EP_IMAGE=//p' .env 2>/dev/null)
fi
if [ -z "$image" ] && [ -f compose.lab.yml ]; then
  image=$(sed -n 's/^[[:space:]]*image:[[:space:]]*//p' compose.lab.yml | head -n 1)
fi
image=${image:-localhost/emuplane:dev}

case "${1:-}" in
  --no-cache) cache=(--no-cache) ;;
  --help|-h)
    sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
    ;;
  "") cache=() ;;
  *)
    echo "unknown option: $1 (try --no-cache)" >&2
    exit 2
    ;;
esac

started=$(date +%s)
podman build --layers "${cache[@]}" -t "$image" .
elapsed=$(( $(date +%s) - started ))

printf '\nbuilt %s in %ss, %s\n' "$image" "$elapsed" \
  "$(podman images --format '{{.Size}}' "$image" | head -n 1)"
