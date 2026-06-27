# DR-0001: Wire BM25 Search Into Dashboard

Date: 2026-06-27
Status: Accepted
Session: persona-brainstorm-20260627-001
Node location: `search/corpus.py` (CODE) + `render/gateway.py` (GATEWAY) + `render/news.py` (CODE)
Depends on: DR-0004 (node-discipline restructure)

## Context

`scripts/search-index.py` builds a BM25 index and synonym map every run (step 8 of 11).
`data/synonym_map.json` contains bilingual abbreviation expansions (AS, KPK, Prabowo, etc.).
The dashboard search box runs `txt.includes(q)` — a naive substring match on rendered card
text. It cannot handle Indonesian abbreviations, bilingual queries, or multi-term lookups.
Judah built BM25 specifically to fix this but it's never used in the UI. The index is
rebuilt every run and thrown away.

## Decision

At dashboard build time, embed the article corpus as a JSON data block in `index.html`.
Upgrade `applyFilters()` to use the synonym map for query expansion before matching.
Replace the substring match with a scored search over title + description + keywords + excerpt.

## What to Build (v1)

- `scripts/build-dashboard.py`: serialize article corpus (id, title, description, excerpt,
  keywords, source, category, lang) as `<script id="article-corpus" type="application/json">`
  embedded in `index.html`
- `scripts/build-dashboard.py`: embed `synonym_map.json` contents as
  `<script id="synonym-map" type="application/json">`
- `dashboard/index.html` JS: on search input, expand query terms via synonym map, then
  score each card by how many expanded terms appear in its corpus entry; sort/filter by score
- Minimum match threshold: at least one expanded term must match for a card to show
- No external JS library — use the already-embedded data

## What Is Deliberately Excluded

- No full BM25 scoring in JavaScript (BM25Okapi requires Python or a JS port) — use
  weighted term frequency as a proxy: title match counts more than excerpt match
- No server required — fully static, no HTTP endpoint
- No search-as-you-type debounce tuning (keep existing oninput trigger)
- No search result ranking UI (no score display, just filter-in/filter-out)
- No cross-tab search (World News only; Football tab search deferred)

## Why This Is High-Impact

Judah searches for "KPK" expecting corruption articles. Gets zero results because Indonesian
articles say "Komisi Pemberantasan Korupsi". He searches "economy" expecting CNBC Indonesia
articles in bahasa. Gets zero. The synonym map already has these expansions — the fix is
embedding it in the page and using it in the filter function. Searching becomes the primary
navigation tool it was intended to be.

## Verification

- [ ] Searching "KPK" returns articles containing "Komisi Pemberantasan Korupsi"
- [ ] Searching "Prabowo" returns articles containing "Presiden Prabowo Subianto"
- [ ] Searching "economy" returns Indonesian-language economics articles
- [ ] Existing source/category filters still work in combination with the new search
- [ ] Empty state still shows when no articles match
- [ ] No visible flash or layout shift when corpus JSON is embedded
