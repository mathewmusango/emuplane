# ministackctl

Operator CLI for the MiniStack control plane, in Rust. It is the fast, typed path
for the same operations the console performs — useful for scripting and for
checking a change without a browser.

```sh
cd cli
cargo build --release
export MC_CONSOLE=https://ministack.mus.com
export MC_ADMIN_TOKEN=…        # or --token-file

./target/release/ministackctl whoami
./target/release/ministackctl accounts
./target/release/ministackctl browse --account 111111111111 --service s3
./target/release/ministackctl exec --account 111111111111 --service s3 \
  --operation create-bucket --param Bucket=logs
./target/release/ministackctl s3-ls --account 111111111111 --bucket logs
```

The lab CA is not in the public root store, so point at it once:

```sh
export MC_CA_FILE=/srv/myinfra/containers/step-ca/root_ca.crt
```

## Security notes

- The token comes from the environment or a file, **never argv**, and is never
  printed. Prefer `--token-file` with mode `0600`.
- TLS verification is on; `--ca-file` only *adds* a root, it never disables it.
- No shell is invoked, so parameter values cannot be interpreted as commands.
- `--json` prints raw API payloads for piping into `jq`.
