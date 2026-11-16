#!/usr/bin/env bash
# Regenerate the browser icons from one source image into web/public/.
set -euo pipefail

cd "$(dirname "$0")/.."

source=${1:-web/public/emuplane.png}
out=web/public

if [ ! -f "$source" ]; then
  echo "no such image: $source" >&2
  exit 1
fi

render() {
  # `-strip` drops metadata, and a flat mark survives `-colors 256` intact while
  # shrinking the 512px file by roughly three quarters. A gradient-heavy mark can
  # lose the palette step — remove `-colors 256` here if banding shows.
  magick -background none "$source" -resize "${1}x${1}" \
    -gravity center -extent "${1}x${1}" -strip -colors 256 \
    -define png:compression-level=9 -define png:compression-filter=5 "$2"
}

render 32 "$out/favicon-32.png"
render 180 "$out/apple-touch-icon.png"
render 192 "$out/favicon-192.png"
render 512 "$out/favicon-512.png"
magick -background none "$source" -strip -define icon:auto-resize=48,32,16 \
  "$out/favicon.ico"

printf 'icons written from %s:\n' "$source"
ls -1 "$out"/favicon-32.png "$out"/favicon-192.png "$out"/favicon-512.png \
  "$out"/apple-touch-icon.png "$out"/favicon.ico
