#!/usr/bin/env bash
# Create the my-labs realm and the ministack-control OIDC client in Keycloak.
#
#   ./scripts/keycloak-realm.sh
#
# Idempotent. Requires the keycloak service running and its admin credentials
# in ../keycloak/.env (KC_BOOTSTRAP_ADMIN_USERNAME / _PASSWORD). The client
# secret is written to the gitignored .env, never printed.
set -euo pipefail

cd "$(dirname "$0")/.."

kc_container=${KC_CONTAINER:-security-keycloak}
kc_env=${KC_ENV:-../keycloak/.env}
realm=${OIDC_REALM:-my-labs}
client_id=${OIDC_CLIENT_ID:-ministack-control}
redirect_uri=${OIDC_REDIRECT_URI:-http://127.0.0.1:4570/oidc/callback}
origin=$(printf '%s' "$redirect_uri" | sed -E 's#^(https?://[^/]+).*#\1#')

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

if kcadm get clients -r "$realm" -q clientId="$client_id" --fields id 2>/dev/null |
  grep -q '"id"'; then
  echo "client exists: $client_id"
else
  kcadm create clients -r "$realm" \
    -s clientId="$client_id" \
    -s enabled=true \
    -s publicClient=false \
    -s standardFlowEnabled=true \
    -s directAccessGrantsEnabled=false \
    -s serviceAccountsEnabled=false \
    -s "redirectUris=[\"$redirect_uri\"]" \
    -s "webOrigins=[\"$origin\"]"
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
out = []
replaced = False
for line in lines:
    if line.startswith("OIDC_CLIENT_SECRET="):
        out.append("OIDC_CLIENT_SECRET=" + secret)
        replaced = True
    else:
        out.append(line)
if not replaced:
    out.append("OIDC_CLIENT_SECRET=" + secret)
path.write_text("\n".join(out) + "\n")
print("wrote OIDC_CLIENT_SECRET to .env")
PY

printf 'realm %s / client %s ready\n' "$realm" "$client_id"
printf 'next: set MINISTACK_AUTH_MODE=oidc (or both) in .env and recreate the control container\n'
