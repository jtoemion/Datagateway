# Datagateway — PRD & Context Document

**Last updated:** 2026-06-27
**Status:** Living document — update after each session
**Runtime:** Hermes agent system — node-discipline (TRIGGER/CODE/GATEWAY) applies to all implementation

---

## What This Is

Personal OSINT daily news aggregator. Fetches RSS from Indonesian and international
portals + TheRundown API for football match data. Stores everything in SQLite + Markdown.
Outputs a static HTML dashboard served locally.

**Sole user:** Judah (builder + reader). No multi-user surface.

---

## Architecture

```
config.yaml          ← source definitions (not currently used by fetch-news.py — see Contradictions)
run.sh               ← 11-step sequential pipeline (set -euo pipefail)
scripts/
  database.py        ← SQLite layer, all table init + CRUD
  fetch-news.py      ← RSS fetcher, 30-min cache, hardcoded SOURCES list
  fetch-football.py  ← TheRundown API (football match events + odds)
  scrape-article.py  ← Full HTML scraper, per-source CSS selectors
  enrich-metadata.py ← sections, keywords, entities, word_count, reading_time
  auto-meta.py       ← fallback enricher for articles with no scraped content
  search-index.py    ← Builds BM25 index → data/search_index.pkl + search_articles.pkl
  search.py          ← BM25 query module (CLI only, not wired to dashboard)
  update-md-content.py ← writes full_text back into .md frontmatter files
  build-dashboard.py ← generates dashboard/index.html
  build-article-viewer.py ← generates dashboard/article.html
  backfill-images.py ← one-shot og:image backfill (not in run.sh)
news/YYYY-MM-DD/     ← .md files per article, one per fetch
dashboard/
  index.html         ← main dashboard (tabs: World News | Football)
  article.html       ← article viewer + vis.js knowledge graph
data/
  search_index.pkl   ← BM25 index
  search_articles.pkl ← article corpus for BM25
  synonym_map.json   ← bilingual synonym map (id/en)
assets/flags/        ← SVG flag icons per country code
datagateway.db       ← SQLite database (gitignored)
```

---

## Database Schema

| Table | Purpose |
|---|---|
| `articles` | Core record: id, source, title, url, description, image_url, date, date_wib, category, lang, filepath, wikilink |
| `sources` | Source registry with etag + last_fetched |
| `scraped_articles` | Full HTML + extracted text per article |
| `article_metadata` | sections[], keywords[], entities[], word_count, reading_time |
| `football_events` | Match schedule/results from TheRundown API |
| `football_odds` | Moneyline/handicap/totals odds per event per sportsbook |
| `cache` | HTTP response cache (30-min TTL) |
| `fetch_log` | Per-run fetch history per source |

---

## Pipeline (11 steps, run.sh)

```
1.  Init DB          ← database.py init_db()
2.  Fetch news       ← fetch-news.py (RSS → articles table)
3.  Fetch football   ← fetch-football.py (TheRundown → football_events + football_odds)
4.  Build dashboard  ← build-dashboard.py (initial pass, before scraping)
5.  Scrape articles  ← scrape-article.py (full text → scraped_articles)
6.  Enrich metadata  ← enrich-metadata.py (sections/keywords/entities → article_metadata)
7.  Auto-meta        ← auto-meta.py --pipeline (catch articles with no scraped content)
8.  Build BM25 index ← search-index.py (pkl files → data/)
9.  Update .md files ← update-md-content.py (writes full_text into .md files)
10. Rebuild dashboard ← build-dashboard.py (now with metadata)
11. Build article viewer ← build-article-viewer.py (article.html + graph data)
```

**Cron schedule (Hermes):**
- 07:00 WIB (00:00 UTC) — job_id `9a2df9644baa`
- 18:00 WIB (11:00 UTC) — job_id `5b4312091c32`

---

## News Sources (fetch-news.py SOURCES — authoritative)

| Source | Lang | Category | Scraping | Notes |
|---|---|---|---|---|
| CNN Indonesia | id | umum | ✅ | `.article-detail .article-content` |
| Detik | id | umum | ✅ | `.detail-content` |
| CNBC Indonesia | id | bisnis | ✅ | `.detail-cnt` |
| Antara | id | umum | ✅ | `.post-content` |
| Republika | id | umum | ✅ | `.article-content` |
| BBC Indonesia | id | internasional | ✅ | `[data-component="text-block"]` |
| BBC News | en | internasional | ✅ | `[data-component="text-block"]` |
| NY Times | en | internasional | ❌ 403 paywall | Always fails scraping; stays in source list |
| BBC Football | en | football | ✅ | Shown in Football tab news section |
| Sky Sports Football | en | football | ✅ | Shown in Football tab news section |
| The Guardian Football | en | football | ✅ | Shown in Football tab news section |
| Fox Sports Soccer | en | football | (partial) | Via API key |
| NY Times Soccer | en | football | ❌ 403 | Same paywall issue |

**Max per source per run:** 15 articles

**Dead RSS (never add back):**
- Kompas: `rss.kompas.com` → HTML not RSS
- Tempo: `rss.tempo.co` → HTTP 403
- Liputan6: `rss.liputan6.com/rss` → HTTP 404
- Okezone: `rss.okezone.com` → DNS fail
- Reuters: `reutersagency.com/feed/` → HTTP 404

---

## Dashboard Features

### World News Tab
- Card grid: image, source badge, date, title, excerpt, keyword badges, reading time, section tags
- Filters: by source (buttons), by category (buttons)
- Search: client-side text filter on title + excerpt + source text (NOT BM25)
- Stats strip: today count, total, sources, latest date
- Wikilink copy button per card (Obsidian integration)
- Article viewer link: `article.html?id=<id>`
- External link to original article

### Football Tab
- Hero card: next match (or latest) with flags, score/vs display, live/FT/scheduled badge
- Carousel: all matches in schedule order
- Odds table: moneyline per sportsbook (DraftKings, BetMGM, FanDuel) with Away/Draw/Home
- Football news section: RSS football articles below match cards (BBC Football, Sky Sports, etc.)

### Article Viewer (article.html)
- Left panel: full scraped article text with images
- Right panel: vis.js force-directed graph
  - Nodes: all articles, colored by source
  - Edges: same source (blue), same category (green), same date (yellow)
  - Click node → navigate to that article

---

## What Works

- RSS fetch + cache: all 8 news sources reliably deliver 15 articles each
- Scraping: 7/8 news sources fully scraped (NY Times always fails)
- Football: TheRundown API delivers events + odds; hero card + carousel + odds table work
- Metadata enrichment: sections, keywords, entities, word_count, reading_time displayed
- Dashboard renders correctly; filter + search work client-side
- Article viewer + graph: loads, navigates between articles
- Cron: twice-daily runs unattended
- BM25 index: builds correctly, .pkl files written

---

## What Doesn't Work / Is Disconnected

### BM25 Search Not Wired to Dashboard
`data/search_index.pkl` exists and is rebuilt every run. Dashboard search ignores it —
uses client-side `txt.includes(q)` on rendered card text. `search.py` is a CLI module
only. No HTTP endpoint, no JS integration.

**Impact:** Multi-word queries, synonym expansion (Prabowo → Presiden Prabowo Subianto),
bilingual cross-language search — all inaccessible to the user from the dashboard.

### config.yaml Is a Dead Config
`config.yaml` defines sources but `fetch-news.py` has its own hardcoded `SOURCES` list
and never reads the YAML file. The two are out of sync. config.yaml has 8 sources;
fetch-news.py has 13.

**Impact:** Editing config.yaml has no effect. Misleading to any reader.

### NY Times Always Fails, Never Flagged
NY Times (`en, internasional`) and NY Times Soccer are in SOURCES but always return 403.
RSS fetch succeeds (returns headlines), but scraping always fails. No dashboard indicator
of this. Articles appear in the grid with no full text.

### SECTION_KEYWORDS Duplicated
`enrich-metadata.py` defines `SECTION_KEYWORDS` dict. `auto-meta.py` defines `SECTION_MAP`
separately — same concept, different keyword lists. Both run in the pipeline. They can
produce different section labels for the same article depending on which runs last.

### README Is Stale
README says 7-step pipeline and lists 11 sources. Actual pipeline is 11 steps; actual
source count is 13. Session notes also say 7 steps (written before the latest expansion).

### .md Files Grow Unboundedly
`news/YYYY-MM-DD/` accumulates indefinitely. No retention policy. The `update-md-content.py`
script rewrites full article text into them every run.

---

## Known Decisions / Tradeoffs

| Decision | Why |
|---|---|
| Static HTML, no server | Simplicity — cron + file output, no process to manage |
| SQLite not Postgres | Single-user, local-first |
| BM25 not semantic search | No API cost, offline, fast enough |
| client-side search in dashboard | No server needed for basic substring match |
| trafilatura for content extraction | Replaces brittle per-source CSS selectors; algorithmic, zero token cost, 0.1–0.2s/article |
| opencode web_fetch as fallback only | Handles JS-heavy pages but slow (~3–5s); only fires when trafilatura returns < 150 words |
| RSS as URL signal only | Full text always from article page, never from RSS description body |
| 15 articles/source cap | Balance freshness vs DB growth |
| set -euo pipefail in run.sh | Fail fast — don't build a half-baked dashboard |

---

## Open Questions (not yet decided)

1. Should BM25 be exposed in the dashboard? If so: pre-render search results into HTML
   at build time, or run a local HTTP server?
2. Should config.yaml be the authoritative source list, with fetch-news.py reading it?
3. NY Times: remove from sources entirely, or keep for RSS headlines with a "no full text" badge?
4. Retention policy for news/ .md files? How many days to keep?
5. SECTION_KEYWORDS: merge into one canonical definition shared by both scripts?
6. Mobile view: dashboard currently desktop-first despite `maximum-scale=1.0` viewport.

---

---

## Node Architecture (Target — node-discipline)

Datagateway runs in the Hermes agent system. Every script is a node with exactly one role:
TRIGGER (starts the flow), CODE (pure IO or computation, no branching), or GATEWAY
(routes, merges, shapes — the only place `if/for-source/category` logic lives).

### Target Node Map

```
TRIGGER
  run.sh                     ← pipeline entry point, invoked by Hermes cron

GATEWAY
  pipeline_gateway.py        ← orchestrates all steps, owns error handling + health write
  sources/gateway.py         ← reads config.yaml, decides which sources to activate,
                               dispatches to fetch/rss.py or fetch/football.py per type
  fetch/extract_gateway.py   ← iterates unscraped articles, calls fetch/extractor.py,
                               writes results to scraped_articles, handles retry + skip
  render/gateway.py          ← MERGE: news + football events + metadata → routes to
                               news renderer, football renderer, article viewer

CODE — DAL
  database.py                ← SQLite DAL (keep as-is; one file, all tables)

CODE — fetch/
  fetch/rss.py               ← pure RSS fetch for one URL → list of article stubs
                               (id, title, url, date, image_url only — no content)
  fetch/football.py          ← TheRundown API client (events + odds for one date range)
  fetch/extractor.py         ← full article extraction: trafilatura primary,
                               opencode web_fetch fallback if word_count < 150
  fetch/web_fetcher.py       ← CODE: subprocess wrapper for opencode web_fetch
                               (fallback only — fires when trafilatura returns nothing)

  NOTE: scrape/ package does not exist. trafilatura replaces BeautifulSoup + CSS selectors.
        RSS is a URL signal only — content always fetched from article page, not RSS body.

CODE — enrich/
  enrich/taxonomy.py         ← one canonical SECTION_KEYWORDS definition (shared)
  enrich/metadata.py         ← section/keyword/entity computation from scraped text
  enrich/auto.py             ← fallback enrichment from title + description only

CODE — search/
  search/indexer.py          ← BM25 index builder → data/search_index.pkl
  search/query.py            ← BM25 query + synonym expansion (CLI or importable)
  search/corpus.py           ← serialize article corpus + synonym map for dashboard embed

CODE — render/
  render/news.py             ← HTML for news card grid + filter bar
  render/football.py         ← HTML for football hero + carousel + odds + news section
  render/article.py          ← HTML for article viewer + vis.js graph
  render/health_badge.py     ← reads last_run.json → renders ✅/⚠️ header badge

CODE — health/
  health.py                  ← writes data/last_run.json on successful pipeline completion
```

### Current Violations (what the refactor must fix)

| File | Violation | Node-discipline rule broken |
|---|---|---|
| `fetch-news.py` | Hardcoded SOURCES list (config management) + RSS fetch in one file | Two roles: GATEWAY config routing + CODE fetch |
| `scrape-article.py` | Entire file replaced by `fetch/extractor.py` (trafilatura) | BeautifulSoup + CSS selectors deleted entirely |
| `build-dashboard.py` (917 lines) | MERGE (news+football), IF (category routing), SET (data shaping), HTML render — all one file | GATEWAY merge/route must separate from CODE render |
| `enrich-metadata.py` + `auto-meta.py` | Duplicate SECTION_KEYWORDS / SECTION_MAP definitions | Two CODE nodes diverging on shared data — consolidate into `enrich/taxonomy.py` |

### Content Extraction Strategy

RSS is a **signal only** — provides article URLs, titles, dates, image URLs.
Full article text always comes from fetching the article page directly.

```
fetch/extractor.py (CODE)
  PRIMARY:   trafilatura.fetch_url(url) + trafilatura.extract(html)
             → pure Python, algorithmic, zero token cost
             → 0.1–0.2s per article, handles all server-rendered sources
             → returns clean plain text (300–900 words for Indonesian/intl news)

  FALLBACK:  opencode run --model opencode/minimax-m3-free "<web_fetch prompt>"
             → only when trafilatura returns None OR word_count < 150
             → handles JS-heavy pages / bot-blocked sites
             → token cost: ~0 in normal operation (current sources are all server-rendered)
             → NY Times paywall still blocks both paths (keep scrape: false in config)
```

**Benchmark (live, 2026-06-27):**

| Source | Words | Time |
|---|---|---|
| Antara | 320 | 0.1s |
| BBC News | 886 | 0.1s |
| CNN Indonesia | 404 | 0.2s |

### YAGNI Gate

Splits are justified when ≥2 consumers OR independent change rate. All violations above
pass: extract_gateway vs extractor have different change rates (gateway owns retry/skip
logic that changes, extractor is stable pure-IO); render nodes independently consumed by
different dashboard tabs; taxonomy consumed by both enrich scripts.

---

## Session Log

| Date | Session | Output |
|---|---|---|
| 2026-06-27 | context-amortization | This document |
| 2026-06-27 | persona-brainstorm-001 | DR-0001, DR-0002, DR-0003 |
| 2026-06-27 | architecture | DR-0004 node-discipline, trafilatura decision |
| 2026-06-27 | intelligence layers | DR-0005 entity, DR-0006 signal, DR-0007 Hermes writer, DR-0008 carousel |
| 2026-06-27 | UI design review | `docs/DESIGN.md` — signal-first redesign plan (P1–P6, DR-0009/10/11 proposed) |
| 2026-06-27 | tradecraft hardening | DR-0012 provenance-aware confidence (revises DR-0006 scoring + DR-0007 auto-publish) |
