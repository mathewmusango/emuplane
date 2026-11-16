#!/usr/bin/env bash
# Capture a Firefox profile of a page load, to open at profiler.firefox.com.
#
#   ./scripts/profile-login.sh                       # the sign-in page
#   ./scripts/profile-login.sh https://emuplane.example.com/  [output.json]
#
# This uses Firefox's own Gecko profiler through the environment variables the
# browser exposes for automation, so the file is a real profile — threads,
# samples, stacks and libraries — not a synthetic summary:
#
#   MOZ_PROFILER_STARTUP          start sampling at launch
#   MOZ_PROFILER_STARTUP_INTERVAL sampling interval in ms (1 = every tick)
#   MOZ_PROFILER_SHUTDOWN         write the profile here on exit
#
# Headless Firefox exits as soon as the screenshot is taken, which is what
# produces a bounded, single-page-load capture. A release build honours these
# variables; a build that does not writes nothing, and this script says so.
#
# Then: https://profiler.firefox.com → "Load a profile from file".
set -euo pipefail

cd "$(dirname "$0")/.."

url=${1:-http://127.0.0.1:4570/login}
out=${2:-my-docs/profile.json}

# The profile directory must exist and carry the CA pref, or Firefox exits
# before loading anything.
profile=$(mktemp -d)
printf 'user_pref("security.enterprise_roots.enabled", true);\n' > "$profile/user.js"
mkdir -p "$(dirname "$out")" "my-docs"
shot="$PWD/my-docs/profile-shot.png"

MOZ_PROFILER_STARTUP=1 \
MOZ_PROFILER_STARTUP_INTERVAL=1 \
MOZ_PROFILER_SHUTDOWN="$PWD/$out" \
  firefox --headless --no-remote --profile "$profile" \
    --window-size=430,900 --screenshot "$shot" "$url" >/dev/null 2>&1 || true

rm -rf "$profile"

if [ ! -s "$out" ]; then
  echo "no profile was written — this Firefox build may not honour MOZ_PROFILER_STARTUP" >&2
  exit 1
fi

printf 'profile: %s (%s)\n' "$out" "$(du -h "$out" | cut -f1)"
printf 'open https://profiler.firefox.com and choose "Load a profile from file"\n'
