# DR-0002: Make config.yaml the Authoritative Source List

Date: 2026-06-27
Status: Accepted
Session: persona-brainstorm-20260627-001
Node location: `config.yaml` (data) + `sources/gateway.py` (GATEWAY) + `fetch/rss.py` (CODE)
Depends on: DR-0004 (node-discipline restructure)

## Context

`config.yaml` is described in README as "Sumber RSS & pengaturan" but `fetch-news.py`
ignores it — it has a hardcoded `SOURCES` list of 13 entries. `config.yaml` has 8.
The two are out of sync and diverging. Editing config.yaml has no effect. Adding a new
source requires editing Python code.

## Decision

Make `config.yaml` the sole authoritative source list. `fetch-news.py` reads sources from
`config.yaml` at startup. The hardcoded `SOURCES` list in `fetch-news.py` is removed.

## What to Build (v1)

- `config.yaml`: add the 5 missing football sources (BBC Football, Sky Sports Football,
  The Guardian Football, Fox Sports Soccer, NY Times Soccer) with correct lang/category.
  Mark NY Times and NY Times Soccer with `scrape: false` to skip scraping without
  removing them from the source list (RSS headlines still fetched).
- `scripts/fetch-news.py`: load sources with
  `yaml.safe_load(open(REPO_ROOT / 'config.yaml'))['sources']` at startup.
  Remove hardcoded `SOURCES` list entirely.
- Keep `max_articles_per_source` and `gnews` config blocks — they're already in config.yaml
  and can be read by the same load call.

## What Is Deliberately Excluded

- No validation schema for config.yaml (trust the YAML structure)
- No hot-reload / watch mode — config is read once at startup per run
- No merging with environment variables or CLI flags
- No migration of other scripts — only fetch-news.py reads source config

## Why This Is High-Impact

Adding a new source is a safe YAML edit, not a Python code change. Removing a dead source
(like NY Times) is one line delete in config.yaml. The `scrape: false` flag lets Judah
keep NY Times RSS headlines while stopping the scraper from wasting time on 15 guaranteed
403s per run. Currently there's no way to do this without editing two files in two languages.

## Verification

- [ ] `python3 scripts/fetch-news.py` reads sources from config.yaml (not hardcoded list)
- [ ] Adding a new source to config.yaml and running fetch-news.py fetches that source
- [ ] Removing a source from config.yaml stops it from being fetched
- [ ] `scrape: false` flag causes scrape-article.py to skip those articles
- [ ] config.yaml and fetch-news.py no longer disagree on source count
