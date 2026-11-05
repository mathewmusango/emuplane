#!/usr/bin/env bash
# Create (or converge) the my-labs realm and the ministack-control OIDC client.
#
#   ./scripts/keycloak-realm.sh
#
# Idempotent: it creates what is missing, then makes sure the client accepts the
# console's current public redirect (plus loopback) and that its home URL is the
# console's public URL. Everything else on the client is left untouched.
# Requires the keycloak service running and its admin credentials in
# ../keycloak/.env (KC_BOOTSTRAP_ADMIN_USERNAME / _PASSWORD). The client secret
# is written to the gitignored .env, never printed.
set -euo pipefail

cd "$(dirname "$0")/.."

kc_container=${KC_CONTAINER:-security-keycloak}
kc_env=${KC_ENV:-../keycloak/.env}
realm=${MC_OIDC_REALM:-$(sed -n 's/^MC_OIDC_REALM=//p' .env | tail -n 1)}
realm=${realm:-my-labs}
client_id=${MC_OIDC_CLIENT_ID:-$(sed -n 's/^MC_OIDC_CLIENT_ID=//p' .env | tail -n 1)}
client_id=${client_id:-ministack-control}
public_url=${MC_PUBLIC_URL:-$(sed -n 's/^MC_PUBLIC_URL=//p' .env | tail -n 1)}
public_url=${public_url:-https://ministack-control.mus.com}
redirect_uri=${MC_OIDC_REDIRECT_URI:-$(sed -n 's/^MC_OIDC_REDIRECT_URI=//p' .env | tail -n 1)}
redirect_uri=${redirect_uri:-$public_url/oidc/callback}
loopback=http://127.0.0.1:4570
origin=$(printf '%s' "$public_url" | sed -E 's#^(https?://[^/]+).*#\1#')

value() {
  sed -n "s/^$1=//p" "$kc_env" | tail -n 1
}

user=$(value KC_BOOTSTRAP_ADMIN_USERNAME)
[ -n "$user" ] || user=$(value KEYCLOAK_ADMIN)
password=$(value KC_BOOTSTRAP_ADMIN_PASSWORD)
[ -n "$password" ] || password=$(value KEYCLOAK_ADMIN_PASSWORD)
if [ -z "$user" ] || [ -z "$password" ]; then
  echo "admin credentials not found in $kc_env" >&2
  exit 1
fi

kcadm() {
  podman exec -i "$kc_container" /opt/keycloak/bin/kcadm.sh "$@"
}

if ! podman container exists "$kc_container"; then
  echo "container $kc_container does not exist; start services/keycloak first" >&2
  exit 1
fi

kcadm config credentials \
  --server http://localhost:8080 --realm master \
  --user "$user" --password "$password"

if kcadm get "realms/$realm" >/dev/null 2>&1; then
  echo "realm exists: $realm"
else
  kcadm create realms -s realm="$realm" -s enabled=true
  echo "created realm: $realm"
fi

uuid=$(kcadm get clients -r "$realm" -q clientId="$client_id" \
  --fields id --format csv 2>/dev/null | tail -n 1 | tr -d '"' || true)
if [ -n "$uuid" ] && [ "$uuid" != "id" ]; then
  echo "client exists: $client_id"
  # Merge the redirect URIs instead of replacing them: the loopback redirect is
  # still how a local `wetty`-style client or the CLI documents signing in, and
  # an operator may have added URIs in the console.
  kcadm get "clients/$uuid" -r "$realm" > /tmp/${client_id}.json
  python3 - "/tmp/${client_id}.json" "$redirect_uri" "$loopback" "$public_url" <<'PY'
import json
import sys

path, redirect_uri, loopback, public_url = sys.argv[1:5]
with open(path, encoding="utf-8") as handle:
    client = json.load(handle)
uris = list(client.get("redirectUris") or [])
for wanted in (loopback + "/oidc/callback", redirect_uri):
    if wanted not in uris:
        uris.append(wanted)
origins = list(client.get("webOrigins") or [])
for wanted in (loopback, public_url):
    if wanted not in origins:
        origins.append(wanted)
client["redirectUris"] = uris
client["webOrigins"] = origins
client["rootUrl"] = public_url
client["baseUrl"] = public_url
with open(path, "w", encoding="utf-8") as handle:
    json.dump(client, handle)
print("redirect URIs:", ", ".join(uris))
PY
  # kcadm runs inside the container, so the body has to come in over stdin.
  kcadm update "clients/$uuid" -r "$realm" -f - < "/tmp/${client_id}.json"
  echo "updated client: $client_id"
else
  kcadm create clients -r "$realm" \
    -s clientId="$client_id" \
    -s enabled=true \
    -s publicClient=false \
    -s standardFlowEnabled=true \
    -s directAccessGrantsEnabled=false \
    -s serviceAccountsEnabled=false \
    -s "rootUrl=$public_url" \
    -s "baseUrl=$public_url" \
    -s "redirectUris=[\"$loopback/oidc/callback\",\"$redirect_uri\"]" \
    -s "webOrigins=[\"$loopback\",\"$origin\"]"
  echo "created client: $client_id"
fi

secret=$(kcadm get clients -r "$realm" -q clientId="$client_id" \
  --fields secret --format csv | tail -n 1 | tr -d '"')
if [ -z "$secret" ]; then
  echo "could not read the client secret" >&2
  exit 1
fi

python3 - "$secret" <<'PY'
import pathlib
import sys

secret = sys.argv[1]
path = pathlib.Path(".env")
lines = path.read_text().splitlines() if path.exists() else []
out, replaced = [], False
for line in lines:
    if line.startswith("MC_OIDC_CLIENT_SECRET="):
        out.append("MC_OIDC_CLIENT_SECRET=" + secret)
        replaced = True
    elif line.startswith("OIDC_CLIENT_SECRET="):
        continue  # pre-rename key, superseded
    else:
        out.append(line)
if not replaced:
    out.append("MC_OIDC_CLIENT_SECRET=" + secret)
path.write_text("\n".join(out) + "\n")
print("wrote MC_OIDC_CLIENT_SECRET to .env")
PY

printf 'realm %s / client %s ready\n' "$realm" "$client_id"
printf 'redirect URIs include: %s\n' "$redirect_uri"
printf 'next: set MC_AUTH_MODE=oidc (or both) in .env and recreate the control container\n'
rm -f "/tmp/${client_id}.json"
