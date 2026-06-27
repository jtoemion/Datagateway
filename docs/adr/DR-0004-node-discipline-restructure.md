# DR-0004: Node-Discipline Restructure — TRIGGER / CODE / GATEWAY

Date: 2026-06-27
Status: Accepted
Session: persona-brainstorm-20260627-001 (addendum)

## Context

Datagateway runs inside the Hermes agent system. Hermes agents invoke scripts as nodes
in a flow. The current `scripts/` layout is a flat collection of 12 scripts with mixed
responsibilities — GATEWAY routing logic (which source, which selector, which tab) is
embedded inside CODE nodes (fetcher, scraper, dashboard builder). This makes each script
harder to test, harder for an agent to partially invoke, and causes the duplication of
shared data (SECTION_KEYWORDS in two files).

Additionally: RSS feed is a URL signal only. Full article content is fetched directly
from the article page using `trafilatura` (algorithmic, zero token cost, 0.1–0.2s/article).
`scrape-article.py` and its BeautifulSoup + CSS selector approach are replaced entirely.
`opencode web_fetch` is a documented fallback for JS-heavy pages, not the primary path.

Node-discipline (TRIGGER/CODE/GATEWAY) is the governing architecture rule for all
Hermes-targeted projects. It is not applied here yet.

## Decision

Restructure `scripts/` into domain packages with node roles made explicit.
Each file gets exactly one role. Branching / routing / merging moves to GATEWAY files.
Pure IO and computation stays in CODE files.

## What to Build (v1 — domain packages)

```
scripts/
  database.py              ← CODE/DAL (keep, no changes needed)
  health.py                ← CODE: writes data/last_run.json (new, for DR-0003)

  sources/
    __init__.py
    gateway.py             ← GATEWAY: reads config.yaml, yields active Source objects,
                              dispatches to fetch/rss or fetch/football based on source type

  fetch/
    __init__.py
    rss.py                 ← CODE: fetch one RSS URL → list of article stubs
                              (id, title, url, date, image_url — NO content from RSS body)
    football.py            ← CODE: fetch TheRundown API → list[FootballEvent], list[Odds]
    extractor.py           ← CODE: url → ExtractResult(full_text, hero_image, body_images[])

                              STEP 1 — fetch HTML
                                html = trafilatura.fetch_url(url)

                              STEP 2 — hero image (og:image / structured data)
                                meta = trafilatura.extract_metadata(html, default_url=url)
                                hero_image = meta.image  # replaces backfill-images.py

                              STEP 3 — article text
                                text = trafilatura.extract(html,
                                    include_comments=False,
                                    include_tables=False)

                              STEP 4 — body images (in-position, from XML)
                                xml  = trafilatura.extract(html,
                                    include_images=True,
                                    output_format='xml')
                                graphics = re.findall(r'<graphic src="([^"]+)" alt="([^"]*)"', xml)
                                body_images = _filter_images(graphics, hero_image)

                              STEP 5 — fallback (web_fetcher.py)
                                if not text or len(text.split()) < 150:
                                    text = web_fetcher.fetch(url)  # opencode web_fetch

                              _filter_images(graphics, hero_url) rules:
                                - skip if alt is empty          (logos, decorative)
                                - skip if URL contains logo/icon/avatar/banner/ads/.gif
                                - skip if URL (strip params) == hero_url (already stored)
                                - skip duplicates (same URL, different query params)
                                - cap at MAX_BODY_IMAGES = 8

                              OUTPUT shape → scraped_articles row:
                                full_text    : str
                                images_json  : [{"src": "...", "alt": "..."}, ...]
                                              (body images only; hero stored in articles.image_url)

    web_fetcher.py         ← CODE: url → str via opencode web_fetch (fallback only)
                              opencode run --model opencode/minimax-m3-free "<fetch prompt>"
                              fires only when extractor.py returns word_count < 150

    extract_gateway.py     ← GATEWAY: iterates unscraped articles → extractor.py,
                              writes results to scraped_articles + updates articles.image_url,
                              owns retry (max 2), skip on persistent failure, rate-limit delay

  # scrape/ does NOT exist — trafilatura replaces BeautifulSoup + all CSS selectors
  # backfill-images.py is also deleted — hero image comes from extractor.py meta.image

  enrich/
    __init__.py
    taxonomy.py            ← CODE: one canonical SECTION_KEYWORDS definition (shared source)
    metadata.py            ← CODE: scraped_text → MetadataResult (sections/keywords/entities)
    auto.py                ← CODE: title+description → MetadataResult (fallback, no scrape needed)

  search/
    __init__.py
    indexer.py             ← CODE: article corpus → BM25 index (.pkl write)
    query.py               ← CODE: (query, synonyms) → ranked article list
    corpus.py              ← CODE: articles + synonym_map → JSON for dashboard embed (DR-0001)

  render/
    __init__.py
    news.py                ← CODE: list[Article] → news tab HTML (cards + filter bar)
    football.py            ← CODE: (events, odds, fb_news) → football tab HTML
    article.py             ← CODE: all articles + graph edges → article.html
    health_badge.py        ← CODE: last_run.json → HTML badge string (DR-0003)
    gateway.py             ← GATEWAY: MERGE news + football + metadata, route to renderers,
                              assemble final index.html + article.html

run.sh                     ← TRIGGER: sources/gateway → fetch/extract_gateway →
                              enrich → search → render/gateway → health
```

## Migration Strategy (don't break the cron)

1. Create domain package dirs with `__init__.py` — empty, non-breaking
2. Migrate one domain at a time, starting with `enrich/taxonomy.py` (no consumers to update yet)
3. Update imports in the consuming scripts before removing the old file
4. Keep old scripts as thin shims (`from scripts.enrich.metadata import *`) during transition
   so cron doesn't break mid-migration
5. Remove shims only after all consumers are updated

**Order:** enrich → fetch (extractor + gateway, replacing scrape-article.py) → sources → render → run.sh

## Files Deleted by This DR

| File | Replaced by |
|---|---|
| `scripts/scrape-article.py` | `scripts/fetch/extractor.py` (trafilatura) |
| `scripts/backfill-images.py` | `scripts/fetch/extractor.py` (meta.image) |
| `scripts/enrich-metadata.py` | `scripts/enrich/metadata.py` + `enrich/taxonomy.py` |
| `scripts/auto-meta.py` | `scripts/enrich/auto.py` |
| `scripts/search-index.py` | `scripts/search/indexer.py` |
| `scripts/search.py` | `scripts/search/query.py` |
| `scripts/fetch-news.py` | `scripts/fetch/rss.py` + `scripts/sources/gateway.py` |
| `scripts/fetch-football.py` | `scripts/fetch/football.py` |
| `scripts/update-md-content.py` | `scripts/fetch/extract_gateway.py` (inline) |
| `scripts/build-dashboard.py` | `scripts/render/gateway.py` + `render/news.py` + `render/football.py` |
| `scripts/build-article-viewer.py` | `scripts/render/article.py` |

## What Is Deliberately Excluded

- No change to `database.py` (DAL is already well-structured)
- No change to the external behavior of any pipeline step
- No new features in this DR — purely structural
- No TypeScript/JS rewrite — Python only
- No MCP server registration (can add later)

## Why This Is High-Impact

DR-0001 (BM25 in dashboard) needs `search/corpus.py`.
DR-0002 (config.yaml) needs `sources/gateway.py`.
DR-0003 (run health) needs `health.py` + `render/health_badge.py`.
All three depend on this structure existing. Doing them without DR-0004 means
bolting new code onto the existing violations — the refactor becomes harder, not easier.

A Hermes agent invoking one pipeline step (e.g., just re-render the dashboard) can call
`render/gateway.py` directly without re-running fetch or scrape. That's only possible if
GATEWAY and CODE roles are separated.

## Verification

- [ ] `nd_classify(scripts/)` returns TRIGGER: 1, GATEWAY: 3, CODE: 12+ with no UNKNOWN
- [ ] `nd_scan(scripts/)` returns zero HIGH violations
- [ ] `python3 -c "from scripts.enrich.taxonomy import SECTION_KEYWORDS"` works
- [ ] `python3 -c "from scripts.fetch.extractor import extract_article"` works
- [ ] `python3 -c "from scripts.fetch.extractor import extract_article; print(len((extract_article('https://www.antaranews.com/berita/5625040/') or '').split()))"` returns > 150
- [ ] `scripts/scrape-article.py` is deleted; no import references remain
- [ ] `bash run.sh` completes without error (same output as before restructure)
- [ ] No file imports another CODE node directly (DAL imports only stdlib + database.py)
