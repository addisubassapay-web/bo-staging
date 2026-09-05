# Keep-Alive Guide — Why the Preview Still Sleeps & How to Fix It

## The Problem

The FastAPI backend on this preview environment has an **internal self-ping loop**
(`_self_ping_loop` in `/app/backend/server.py`) that hits its own `/api/health`
endpoint every 90 seconds. That keeps the pod busy so the platform doesn't
mark it idle **while it is already running**.

**But: a self-ping cannot wake a pod that has already been stopped.**

If the Emergent scheduler decides the pod is idle and scales it to zero, the
Python process — including our `_self_ping_loop` task — dies with it. There's
nothing left inside the container to send the next ping. The pod only comes
back when *external* traffic hits the ingress.

Evidence from the log this was diagnosed against:
```
17:02:53  [self-ping] Heartbeat ping status: 200
17:06:23  [self-ping] Heartbeat ping status: 200
...
15:01:31  [self-ping] Heartbeat ping status: 200    ← last ping before sleep
(2-hour dead zone — pod scaled to zero)
17:02:53  [self-ping] Heartbeat ping status: 200    ← woke up on external request
```

## The Fix (must come from OUTSIDE)

Point any always-on uptime monitor at:

```
https://bo-staging.preview.emergentagent.com/api/health
```

Pick one:

### Option A — UptimeRobot (free, 5-min minimum)
1. Sign up at https://uptimerobot.com
2. **Add New Monitor** → *HTTP(s)*
3. URL: `https://bo-staging.preview.emergentagent.com/api/health`
4. Monitoring Interval: **5 minutes**
5. Save. Done. You get free downtime alerts as a bonus.

### Option B — Cron-Job.org (free, 1-min minimum)
1. Sign up at https://cron-job.org
2. **Create cronjob**
3. URL: `https://bo-staging.preview.emergentagent.com/api/health`
4. Schedule: every 4 minutes
5. Save.

### Option C — GitHub Actions cron (free, requires a repo)
Add `.github/workflows/keepalive.yml`:

```yaml
name: Keep BlueOcean Preview Warm
on:
  schedule:
    - cron: '*/5 * * * *'   # every 5 min
  workflow_dispatch:
jobs:
  ping:
    runs-on: ubuntu-latest
    steps:
      - name: Ping /api/health
        run: |
          curl -sS --max-time 15 \
            https://bo-staging.preview.emergentagent.com/api/health \
            | tee /dev/stderr
```

### Option D — Better Stack / Better Uptime / Cronitor / Healthchecks.io
All accept the same URL. Any 5-min HTTPS GET will do the job.

## Verifying It Works

Once the external monitor is running, watch `/var/log/supervisor/backend.err.log`:

```bash
tail -f /var/log/supervisor/backend.err.log | grep -E "GET /api/health|Heartbeat"
```

You should see one line from an *external* IP (the monitor's egress) every N
minutes, in addition to the `[self-ping]` line from `127.0.0.1`.

## Behavior Summary

| Scenario | Internal self-ping (this repo) | External monitor |
|---|---|---|
| Pod is running, idle timer approaching | ✅ prevents idle scale-down | ✅ prevents idle scale-down |
| Pod is already stopped | ❌ can't run (process is gone) | ✅ triggers cold-start via ingress |

The internal loop is still useful — it keeps the pod alive between external
polls and shows up in the enriched heartbeat with `db.latency_ms` and
`mailer.breaker_open` for observability. Just don't rely on it alone.

## Config Reference

| Env Var | Default | Purpose |
|---|---:|---|
| `PREVIEW_URL` | — | External URL the self-ping targets |
| `SELF_PING_INTERVAL_SEC` | `90` | Seconds between internal pings (min 30) |
| `HEALTH_ALERT_WEBHOOK_URL` | — | Slack/Discord webhook for degraded alerts |
| `HEALTH_FORCE_TOKEN` | — | (not required) admin auth handles force-degraded |
