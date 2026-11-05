# Dashboards for ministack.

Drop a Grafana dashboard JSON here and it is provisioned on start —
`services/grafana/scripts/collect.py` copies `addons/grafana/*.json` from every
service into the one directory Grafana mounts.

Three rules, all enforced by that collector:

- the file needs a `uid` and a `title`;
- the `uid` must be unique across the lab (a duplicate silently overwrites
  another dashboard, so it is an error instead);
- the **first panel** (top-left) must be a `stat` titled `Status` querying
  `up{...}` — the up/down box every service dashboard starts with.

`dashboard.json` in this directory is the scaffolded starting point: a single
Status panel for `up{job="ministack"}`. Add your panels to its right; keep it
first. If the service is not scraped, the job name here must match
`addons/prometheus/scrape.yml`.

Point panels at the provisioned datasource by uid:

```json
"datasource": { "type": "prometheus", "uid": "prometheus" }
```
