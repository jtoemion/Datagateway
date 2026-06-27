# DR-0003: Run Health Indicator in Dashboard

Date: 2026-06-27
Status: Accepted
Session: persona-brainstorm-20260627-001
Node location: `run.sh` (TRIGGER) + `health.py` (CODE) + `render/health_badge.py` (CODE)
Depends on: DR-0004 (node-discipline restructure)

## Context

`run.sh` uses `set -euo pipefail` with 11 steps. If any step fails (scraper timeout,
API rate limit, network error), the script aborts. Step 4 writes an initial `index.html`;
step 10 writes the final `index.html` with full metadata. If the run aborts between
steps 5-9, the dashboard header shows `datetime.now()` as "last update" — which
is the step-4 partial build time, not a complete successful run. Judah has no way
to distinguish a good dashboard from a partial one.

## Decision

Write `data/last_run.json` only on fully successful pipeline completion (after step 11).
Dashboard build reads this file and renders a visible run-status badge in the header.
Missing or stale `last_run.json` → warning badge.

## What to Build (v1)

- `run.sh`: after step 11, add final step:
  ```bash
  python3 -c "
  import json, datetime
  d = {'status': 'ok', 'completed_at': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7))).isoformat(), 'steps': 11}
  open('data/last_run.json', 'w').write(json.dumps(d))
  "
  echo "  Run complete: data/last_run.json written"
  ```
- `scripts/build-dashboard.py`: at build time, read `data/last_run.json`.
  - If missing: badge = `⚠️ No completed run on record`
  - If present and `completed_at` is within last 13 hours: badge = `✅ {completed_at} WIB`
  - If present but older than 13 hours: badge = `⚠️ Last run: {completed_at} WIB (stale)`
  - Embed badge in header `.head-info` div next to the existing update timestamp
- 13-hour threshold: cron runs every 11 hours (07:00 + 18:00 WIB). If > 13h since last
  success, something missed.

## What Is Deliberately Excluded

- No per-step status tracking (just "all 11 done" or "not done")
- No error message in the badge (shell stderr is the error log)
- No alert/notification on failure (Judah checks visually)
- No dashboard for failed-run history

## Why This Is High-Impact

A partial build looks identical to a complete build. The timestamp in the header currently
gives false confidence — Judah can read a dashboard that has no keywords, no reading times,
no scraped content, and think the run was fine. A ✅ / ⚠️ badge in the header makes the
health of every run immediately visible on open.

## Verification

- [ ] After a successful `bash run.sh`, `data/last_run.json` exists with `status: ok`
- [ ] Dashboard header shows ✅ badge with timestamp from `last_run.json`
- [ ] If `last_run.json` is deleted, dashboard header shows ⚠️ warning
- [ ] If `last_run.json` is artificially backdated > 13h, dashboard shows stale warning
- [ ] A mid-run abort (kill the process after step 5) leaves the old `last_run.json` —
      dashboard correctly shows stale warning if old enough
