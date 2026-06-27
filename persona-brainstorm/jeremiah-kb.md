# Jeremiah's Knowledge Base — Datagateway

**Domain:** Datagateway — personal OSINT news aggregator
**Last updated:** 2026-06-27
**Sources:** PRD.md, datagateway-session-notes.md, config.yaml, run.sh, scripts/

---

## Product Context

### What the product does today

Twice-daily pipeline fetches 13 RSS sources (Indonesian + international + football),
scrapes full article text, enriches with section tags / keywords / entities / reading time,
and writes a static HTML dashboard. Judah reads the dashboard to stay current on news.
Football tab shows FIFA World Cup match cards with live odds.

### What Judah wants from it

A fast daily read with real signal, not noise. He opens the dashboard in the morning after
the 07:00 WIB cron, scans headlines, clicks into articles that matter. He wants to find
things quickly — by topic, by source, or by searching for something specific.

The Obsidian wikilink copy button suggests Judah also links articles into his notes.

### Known constraints

- No server running between cron runs. Everything is static HTML.
- Single user, local machine. No auth, no sharing requirement.
- set -euo pipefail — one step failure kills the whole run.
- NY Times and NY Times Soccer always fail scraping (403 paywall) but remain in SOURCES.

---

## Who the Users Are

**Judah (sole user + builder)** — reads the dashboard twice a day. Cares about:
- Speed of finding relevant news (search, filter)
- Completeness (all important stories covered, no missing sources)
- Depth (can read full article without leaving the dashboard)
- Signal-to-noise (no broken articles, no empty cards without explanation)

No other users. No sharing surface today.

---

## Pain Today

**Pain 1: Search is crippled.**
BM25 index is built every run. Dashboard search ignores it. Client-side text filter does
`txt.includes(q)` — works for exact substrings, fails for multi-word queries, Indonesian
abbreviations (AS, RI, KPK), synonyms (Prabowo → Presiden Prabowo Subianto), or bilingual
cross-search (searching "economy" to find Indonesian "ekonomi" articles). Judah built BM25
with synonym expansion specifically for this — but can't use it.

**Pain 2: NY Times silently fails, cards appear broken.**
15 NY Times articles appear in the grid every run with RSS headline text but no full
article body. No badge, no indicator. Judah reads a card, clicks "📖 Read", sees empty
content. No way to know from the dashboard that these are always broken.

**Pain 3: config.yaml is a trap.**
Judah edits config.yaml to add/remove sources. Nothing changes. fetch-news.py ignores it.
The real config is the SOURCES list in fetch-news.py. Judah has to remember to edit two
places — or the YAML silently does nothing.

**Pain 4: Pipeline aborts on any single step failure.**
set -euo pipefail means if one of 11 steps fails (e.g., TheRundown API is down, scraper
hits a 429), the entire run aborts. Dashboard is rebuilt in step 10 — if step 5 (scrape)
crashes, the final dashboard is never written and the old one sits there stale.
Judah opens the dashboard, doesn't know it's from yesterday's run.

**Pain 5: No way to know when the last successful run happened.**
Dashboard shows "last update" timestamp (datetime.now() at build time) but this is written
by step 10. If step 4 built an initial dashboard and then steps 5-10 failed, the displayed
timestamp reflects the step-4 partial build, not a complete successful run.

**Pain 6: SECTION_KEYWORDS duplicated, can produce inconsistent labels.**
enrich-metadata.py and auto-meta.py each define their own section taxonomy. An article
can get "POLITIK" from one and "HUKUM" from the other depending on which ran last.
Dashboard section badges reflect the last-written value — Judah can't trust them to be
consistent.

---

## What Jeremiah Can Answer Definitively

- **BM25 used in dashboard?** No. search.py is CLI-only. Dashboard uses substring match.
- **config.yaml authoritative?** No. fetch-news.py SOURCES list is authoritative. YAML not read.
- **NY Times articles have full text?** Never. 403 paywall, always 0/15 scraped. No dashboard indicator.
- **Pipeline survivable if one step fails?** No. set -euo pipefail kills the run.
- **Section labels consistent?** No. Two separate keyword definitions, both can run on same article.
- **Football articles visible?** Yes. In Football tab below match cards, via `football_news_section`.
- **Dashboard shows last successful run?** No. Shows last step-4/step-10 build timestamp.

---

## What Jeremiah Doesn't Know (KB Gaps)

- Whether Judah wants BM25 surfaced inline in the dashboard or prefers a separate search page.
- Whether Judah ever edits config.yaml thinking it works (does he know it's dead?).
- Whether Judah notices or cares about the NY Times broken cards (does he read EN articles?).
- How often the cron actually fails (are partial dashboards a known daily problem?).
- Whether Judah uses the article viewer / vis.js graph in practice.
- What Judah's primary reading flow is: scan grid → read in article.html, or scan grid → click Original?

---

## KB Maintenance

After each session, update with:
- New decisions made (close open questions)
- Gaps resolved (move from "doesn't know" to "can answer")
- New friction surfaced
- Date of update
