#!/usr/bin/env bash
# Capture a Firefox profile of one page load, via MOZ_PROFILER_STARTUP, to open at profiler.firefox.com.
set -euo pipefail

cd "$(dirname "$0")/.."

url=${1:-http://127.0.0.1:4570/login}
out=${2:-my-docs/profile.json}

# The profile directory must exist and carry the CA pref, or Firefox exits before loading anything.
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
