//! `ministackctl` — a small, safe operator for the MiniStack control plane.
//!
//! It talks to the control API over HTTPS with the admin bearer token. The token
//! is read from the environment or a file, never from argv, and is never printed.
//! No shell is involved, so parameters cannot be injected into a command line.

use std::collections::BTreeMap;
use std::fs;
use std::path::PathBuf;
use std::time::Duration;

use anyhow::{bail, Context, Result};
use clap::{Parser, Subcommand};
use reqwest::blocking::{Client, Response};
use serde_json::{json, Value};

#[derive(Parser, Debug)]
#[command(
    name = "ministackctl",
    version,
    about = "Operate the MiniStack control plane"
)]
struct Cli {
    /// Console base URL.
    #[arg(
        long,
        env = "MINISTACK_CONSOLE",
        default_value = "https://ministack.mus.com"
    )]
    console: String,

    /// Admin bearer token. Prefer --token-file or the environment.
    #[arg(long, env = "MINISTACK_ADMIN_TOKEN", hide_env_values = true)]
    token: Option<String>,

    /// File holding the admin bearer token (mode 0600 expected).
    #[arg(long)]
    token_file: Option<PathBuf>,

    /// Extra PEM root certificate (the lab CA), on top of the system store.
    #[arg(long, env = "MINISTACK_CA_FILE")]
    ca_file: Option<PathBuf>,

    /// Print raw JSON instead of a table.
    #[arg(long)]
    json: bool,

    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand, Debug)]
enum Command {
    /// Show the signed-in account and control-plane health.
    Whoami,
    /// List accounts visible to the token.
    Accounts,
    /// List service availability.
    Services,
    /// List resources of one service in one account and region.
    Browse {
        #[arg(long)]
        account: String,
        #[arg(long, default_value = "us-east-1")]
        region: String,
        #[arg(long)]
        service: String,
    },
    /// Run a console action, e.g. s3 create-bucket --param Bucket=logs
    Exec {
        #[arg(long)]
        account: String,
        #[arg(long, default_value = "us-east-1")]
        region: String,
        #[arg(long)]
        service: String,
        #[arg(long)]
        operation: String,
        /// Repeatable key=value parameter.
        #[arg(long = "param", value_parser = parse_param)]
        params: Vec<(String, String)>,
    },
    /// List objects in a bucket.
    S3Ls {
        #[arg(long)]
        account: String,
        #[arg(long, default_value = "us-east-1")]
        region: String,
        #[arg(long)]
        bucket: String,
        #[arg(long, default_value = "")]
        prefix: String,
    },
}

fn parse_param(raw: &str) -> Result<(String, String), String> {
    match raw.split_once('=') {
        Some((key, value)) if !key.trim().is_empty() => {
            Ok((key.trim().to_string(), value.to_string()))
        }
        _ => Err(format!("expected key=value, got {raw:?}")),
    }
}

struct Api {
    client: Client,
    base: String,
    token: String,
}

impl Api {
    fn new(base: &str, token: String, ca_file: Option<&PathBuf>) -> Result<Self> {
        let mut builder = Client::builder().timeout(Duration::from_secs(30));
        if let Some(path) = ca_file {
            let pem = fs::read(path).with_context(|| format!("read {}", path.display()))?;
            let certificate =
                reqwest::Certificate::from_pem(&pem).context("parse CA certificate")?;
            builder = builder.add_root_certificate(certificate);
        }
        let client = builder.build().context("build HTTP client")?;
        Ok(Self {
            client,
            base: base.trim_end_matches('/').to_string(),
            token,
        })
    }

    fn get(&self, path: &str) -> Result<Value> {
        let response = self
            .client
            .get(format!("{}{}", self.base, path))
            .bearer_auth(&self.token)
            .send()
            .with_context(|| format!("GET {path}"))?;
        decode(response)
    }

    fn post(&self, path: &str, body: &Value) -> Result<Value> {
        let response = self
            .client
            .post(format!("{}{}", self.base, path))
            .bearer_auth(&self.token)
            .json(body)
            .send()
            .with_context(|| format!("POST {path}"))?;
        decode(response)
    }
}

fn decode(response: Response) -> Result<Value> {
    let status = response.status();
    let text = response.text().context("read response body")?;
    if !status.is_success() {
        let detail: String = text.chars().take(400).collect();
        bail!("HTTP {status}: {detail}");
    }
    if text.trim().is_empty() {
        return Ok(Value::Null);
    }
    serde_json::from_str(&text).with_context(|| "parse JSON response")
}

fn resolve_token(cli: &Cli) -> Result<String> {
    if let Some(token) = &cli.token {
        return Ok(token.clone());
    }
    if let Some(path) = &cli.token_file {
        let token = fs::read_to_string(path)
            .with_context(|| format!("read {}", path.display()))?
            .trim()
            .to_string();
        if token.is_empty() {
            bail!("token file {} is empty", path.display());
        }
        return Ok(token);
    }
    bail!("no admin token: set MINISTACK_ADMIN_TOKEN or pass --token-file")
}

fn s(value: &Value, key: &str) -> String {
    value
        .get(key)
        .and_then(Value::as_str)
        .unwrap_or("-")
        .to_string()
}

fn browse_path(account: &str, region: &str, service: &str) -> String {
    format!(
        "/api/browse?account={}&region={}&service={}",
        urlencode(account),
        urlencode(region),
        urlencode(service)
    )
}

fn urlencode(value: &str) -> String {
    value
        .bytes()
        .map(|byte| match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                (byte as char).to_string()
            }
            b' ' => "%20".to_string(),
            other => format!("%{other:02X}"),
        })
        .collect()
}

fn main() -> Result<()> {
    let cli = Cli::parse();
    let token = resolve_token(&cli)?;
    let api = Api::new(&cli.console, token, cli.ca_file.as_ref())?;

    match &cli.command {
        Command::Whoami => {
            let meta = api.get("/api/meta")?;
            let me = meta.get("me").cloned().unwrap_or(Value::Null);
            if cli.json {
                println!("{}", serde_json::to_string_pretty(&meta)?);
            } else {
                println!("user      {}", s(&me, "user"));
                println!("account   {}", s(&me, "account"));
                println!("role      {}", s(&me, "role"));
                println!("emulator  {}", s(&meta, "version"));
                println!(
                    "regions   {}",
                    meta.get("regions")
                        .and_then(Value::as_array)
                        .map(|rows| rows
                            .iter()
                            .filter_map(Value::as_str)
                            .collect::<Vec<_>>()
                            .join(", "))
                        .unwrap_or_else(|| "-".into())
                );
            }
        }
        Command::Accounts => {
            let accounts = api.get("/api/users")?;
            if cli.json {
                println!("{}", serde_json::to_string_pretty(&accounts)?);
            } else {
                for account in accounts.as_array().cloned().unwrap_or_default() {
                    println!(
                        "{}  {}  regions=[{}]  global_admin={}",
                        s(&account, "account_id"),
                        s(&account, "alias"),
                        account
                            .get("regions")
                            .and_then(Value::as_array)
                            .map(|rows| rows
                                .iter()
                                .filter_map(Value::as_str)
                                .collect::<Vec<_>>()
                                .join(","))
                            .unwrap_or_default(),
                        account
                            .get("global_admin")
                            .and_then(Value::as_bool)
                            .unwrap_or(false)
                    );
                }
            }
        }
        Command::Services => {
            let services = api.get("/api/services")?;
            if cli.json {
                println!("{}", serde_json::to_string_pretty(&services)?);
            } else {
                for name in services
                    .as_object()
                    .map(|map| map.keys().cloned().collect::<Vec<_>>())
                    .unwrap_or_default()
                {
                    println!("{name}");
                }
            }
        }
        Command::Browse {
            account,
            region,
            service,
        } => {
            let payload = api.get(&browse_path(account, region, service))?;
            if cli.json {
                println!("{}", serde_json::to_string_pretty(&payload)?);
            } else {
                for row in payload
                    .get("resources")
                    .and_then(Value::as_array)
                    .cloned()
                    .unwrap_or_default()
                {
                    println!("{:<14} {}", s(&row, "kind"), s(&row, "name"));
                }
            }
        }
        Command::Exec {
            account,
            region,
            service,
            operation,
            params,
        } => {
            let mut map = BTreeMap::new();
            for (key, value) in params {
                map.insert(key.clone(), Value::String(value.clone()));
            }
            let body = json!({
                "account": account,
                "region": region,
                "service": service,
                "operation": operation,
                "params": map,
            });
            let result = api.post("/api/exec", &body)?;
            if cli.json {
                println!("{}", serde_json::to_string_pretty(&result)?);
            } else {
                let ok = result.get("ok").and_then(Value::as_bool).unwrap_or(false);
                println!(
                    "{} (upstream {})",
                    if ok { "ok" } else { "failed" },
                    result.get("status").and_then(Value::as_i64).unwrap_or(0)
                );
                if let Some(error) = result.get("error").and_then(Value::as_str) {
                    println!("{error}");
                } else if let Some(body) = result.get("body").and_then(Value::as_str) {
                    println!("{}", body.chars().take(2000).collect::<String>());
                }
            }
        }
        Command::S3Ls {
            account,
            region,
            bucket,
            prefix,
        } => {
            let payload = api.get(&format!(
                "/api/s3/objects?account={}&region={}&bucket={}&prefix={}",
                urlencode(account),
                urlencode(region),
                urlencode(bucket),
                urlencode(prefix)
            ))?;
            if cli.json {
                println!("{}", serde_json::to_string_pretty(&payload)?);
            } else {
                for object in payload
                    .get("objects")
                    .and_then(Value::as_array)
                    .cloned()
                    .unwrap_or_default()
                {
                    println!("{:>10}  {}", s(&object, "size"), s(&object, "key"));
                }
            }
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_key_value() {
        assert_eq!(
            parse_param("Bucket=logs").unwrap(),
            ("Bucket".into(), "logs".into())
        );
        assert!(parse_param("nope").is_err());
        assert!(parse_param("=value").is_err());
    }

    #[test]
    fn encodes_path_segments() {
        assert_eq!(urlencode("a b/c"), "a%20b%2Fc");
    }
}
