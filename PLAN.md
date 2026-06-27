# Datagateway — Master Implementation Plan

**For:** the implementing agent (Hermes / opencode-build subagent)
**Date:** 2026-06-27
**Status:** Ready to execute. Plan only — nothing here is built yet.

---

## 0. How To Use This Plan

This is the single execution doc. It sequences every decision record into atomic,
dependency-ordered phases. Read these first, in order:

1. `PRD.md` — what the system is, current state, contradictions, node architecture
2. `docs/DESIGN.md` — the UI redesign (signal-first) and epistemic visual language
3. `docs/adr/DR-0001` … `DR-0008`, `DR-0012` — the specs each phase implements
4. This file — the order, the gates, the done-criteria

### Working rules (non-negotiable — this is a Hermes / node-discipline project)

- **Node discipline.** Every file is exactly one role: TRIGGER / CODE / GATEWAY. CODE nodes
  have zero lateral imports and zero branching on role/status. Branching/merging/shaping
  lives only in GATEWAY nodes. Run `nd_scan(scripts/)` at the end of every phase — zero HIGH
  violations is a merge gate.
- **TDD.** One RED test → minimal GREEN → repeat. Write the failing test first; confirm it
  fails before implementing. Each atomic task ships with at least one test for its new behavior.
- **Atomic tasks.** One diff = one behavior. A task taking >3 TDD cycles is too large — split it.
- **Don't break the cron.** The pipeline runs twice daily. Use the shim strategy (DR-0004
  §Migration) so the old pipeline keeps working until each domain is fully migrated.
- **YAGNI.** Don't split a module until ≥2 consumers or independent change rate (DR-0004 gate).
- **Verify after every phase.** Run `bash run.sh` end-to-end; the dashboard must still build.

### Definition of done (per task)
`RED test written & failing → GREEN impl → full test file passes → nd_scan clean →
git diff reviewed → committed`. Per phase: all tasks done + `bash run.sh` succeeds +
phase verification checklist passes.

---

## 1. Dependency Graph

```
                    ┌─────────────────────────────────────────────┐
   FOUNDATION  ───► │ DR-0004  node-discipline restructure          │
                    └─────────────────────────────────────────────┘
                         │            │            │
        ┌────────────────┼────────────┼────────────┼─────────────────┐
        ▼                ▼            ▼            ▼                  ▼
   DR-0002          DR-0003       DR-0001     DR-0005            (uses trafilatura
   config.yaml      run health    BM25 search entity layer        from DR-0004)
        │                │            │            │
        └────────────────┴────────────┴────────────┤
                                                    ▼
                                          ┌──────────────────────┐
                                          │ DR-0006 signal layer  │
                                          │  + DR-0012 scoring     │ ◄── build together;
                                          │  (provenance-aware)    │     never ship the
                                          └──────────────────────┘     naive scorer
                                                    │
                                                    ▼
                                          ┌──────────────────────┐
                                          │ DR-0007 Hermes writer │
                                          └──────────────────────┘
                                                    │
                                                    ▼
                                          ┌──────────────────────┐
                                          │ DESIGN UI: Briefing,  │
                                          │ epistemic system,     │ (revises DR-0008;
                                          │ Graph, Entities       │  see DESIGN.md P9)
                                          └──────────────────────┘
```

**Critical instruction:** DR-0006 and DR-0012 are implemented as ONE phase. Do **not** build
DR-0006's naive `unique_sources / total` confidence and then rewrite it — build the
provenance-aware scorer (DR-0012) from the start. The naive model is known-broken (it counts
wire reprints as independent corroboration); shipping it even transiently is wasted work.

---

## 2. Phase Order & Rationale

| Phase | DR | Why here | LLM? |
|---|---|---|---|
| **P0** | — | Prereqs: deps, package skeleton, DB migration harness | no |
| **P1** | DR-0004 | Structural foundation; everything imports the new layout | no |
| **P2** | DR-0002 | Smallest; unblocks source management; low risk | no |
| **P3** | DR-0003 | Standalone; makes every later run observable | no |
| **P4** | DR-0001 | Search; pure render/search work, no intel deps | no |
| **P5** | DR-0005 | Entity layer; substrate for clustering | no |
| **P6** | DR-0006 + DR-0012 | Signal layer with provenance-aware scoring (one phase) | no |
| **P7** | DR-0007 | Hermes writer; needs signals + entities | **yes** (Haiku) |
| **P8** | DESIGN UI | Briefing + epistemic visual system + rail revision | no |
| **P9** | DESIGN Graph/Entities (DR-0009/10/11) | Highest-altitude UI; optional for MVP | no |

---

## 3. Phase 0 — Prerequisites & Scaffolding

**Goal:** environment ready, empty package skeleton in place, DB migration runnable. No behavior change.

### Tasks
- **P0.1** Install deps (record in `requirements.txt`):
  ```
  trafilatura          # content extraction (DR-0004) — already installed
  datasketch           # MinHash LSH for provenance (DR-0012)
  rank_bm25            # BM25 search + clustering (DR-0001/0006) — already present
  rapidfuzz            # fuzzy alias matching (DR-0012 §6)
  anthropic            # Hermes writer (DR-0007) — Haiku 4.5
  PyYAML               # config.yaml (DR-0002)
  ```
- **P0.2** Create the package skeleton with empty `__init__.py` (non-breaking):
  ```
  scripts/{sources,fetch,enrich,search,render,signal}/__init__.py
  ```
- **P0.3** Build a tiny migration runner `scripts/migrate.py` (CODE) that applies
  idempotent `ALTER TABLE` / `CREATE TABLE IF NOT EXISTS` statements. All later phases add
  their DDL here. Must be safe to run repeatedly.
- **P0.4** Add a test harness: `tests/` dir, `pytest` config, a fixture DB seeded from a
  frozen snapshot of ~30 real articles across all sources (copy from `datagateway.db`).

### Verification
- [ ] `pip install -r requirements.txt` clean
- [ ] `python3 scripts/migrate.py` runs twice with no error (idempotent)
- [ ] `pytest` collects and runs (even if 0 tests yet)
- [ ] `bash run.sh` still succeeds (skeleton is inert)

---

## 4. Phase 1 — DR-0004 Node-Discipline Restructure

**Goal:** flat `scripts/` → domain packages, one role per file. `scrape-article.py` and
`backfill-images.py` deleted; `fetch/extractor.py` (trafilatura) replaces them.

**Spec:** `docs/adr/DR-0004`. **Migration order:** enrich → fetch → sources → render → run.sh.

### Atomic tasks (each = one module migrated, with shim left behind until consumers updated)
- **P1.1** `enrich/taxonomy.py` — single canonical `SECTION_KEYWORDS` (merge the two duplicate
  defs from `enrich-metadata.py` + `auto-meta.py`). Test: known text → expected sections.
- **P1.2** `enrich/metadata.py` + `enrich/auto.py` — split full-text vs title-only enrichment;
  both import `taxonomy`. Shim old files.
- **P1.3** `fetch/extractor.py` — trafilatura: text + hero image (`meta.image`) + body images
  (XML `<graphic>`), with the image filter (empty-alt / blocklist / hero-dedup / cap 8).
  Test against frozen HTML fixtures per source. **This is the highest-value task** — verify
  word counts match the DR benchmark (Antara ~320, BBC ~886, CNN ~404).
- **P1.4** `fetch/web_fetcher.py` — opencode fallback (only when extractor < 150 words).
- **P1.5** `fetch/extract_gateway.py` (GATEWAY) — iterate unscraped → extractor → write
  `scraped_articles` + update `articles.image_url`; retry≤2, skip on persistent fail.
- **P1.6** `fetch/rss.py` — RSS → stubs only (id/title/url/date/image). No content from body.
- **P1.7** `fetch/football.py` — migrate `fetch-football.py` unchanged in behavior.
- **P1.8** `sources/gateway.py` (GATEWAY) — placeholder reading the hardcoded list for now
  (DR-0002 wires config.yaml next). Dispatches rss vs football by source type.
- **P1.9** `search/{indexer,query,corpus}.py` — migrate `search-index.py` + `search.py`;
  `corpus.py` is new (stub for DR-0001).
- **P1.10** `render/{news,football,article,gateway}.py` — split `build-dashboard.py` (917 lines)
  and `build-article-viewer.py`. GATEWAY merges + routes; CODE files render. Output HTML must
  be byte-stable vs the current dashboard (snapshot test).
- **P1.11** `health.py` — stub (DR-0003 fills it).
- **P1.12** Rewrite `run.sh` to the new TRIGGER order. Delete shims + old scripts once green.

### Gates
- [ ] `nd_classify(scripts/)` → TRIGGER 1, GATEWAY 3, CODE 12+, no UNKNOWN
- [ ] `nd_scan(scripts/)` → 0 HIGH
- [ ] `scrape-article.py`, `backfill-images.py` deleted; no references remain
- [ ] `render/` output diff vs pre-refactor dashboard is empty (snapshot test)
- [ ] `bash run.sh` produces the same dashboard as before

---

## 5. Phase 2 — DR-0002 config.yaml Authoritative

**Goal:** `config.yaml` is the only source list; `sources/gateway.py` reads it.

### Tasks
- **P2.1** Add the 5 football sources to `config.yaml`; add `scrape: false` to NY Times + NYT Soccer.
- **P2.2** `sources/gateway.py` reads `yaml.safe_load(config.yaml)['sources']`; remove hardcoded list.
- **P2.3** `fetch/extract_gateway.py` honors `scrape: false` (skip extraction, keep RSS headline).

### Verification
- [ ] Adding a source in YAML → it gets fetched; removing → it stops
- [ ] `scrape: false` skips extraction for NY Times
- [ ] config.yaml and code no longer disagree on source count

---

## 6. Phase 3 — DR-0003 Run Health Indicator

**Goal:** dashboard shows ✅/⚠️ run-health badge; partial builds are detectable.

### Tasks
- **P3.1** `health.py` writes `data/last_run.json {status, completed_at, steps}` — called as
  the FINAL step of `run.sh` (after step 11), so an aborted run never writes success.
- **P3.2** `render/health_badge.py` reads it → badge string (✅ fresh / ⚠️ stale >13h / ⚠️ missing).
- **P3.3** `render/gateway.py` embeds the badge in the header.

### Verification
- [ ] Successful run writes `last_run.json`; badge shows ✅ + timestamp
- [ ] Deleted/backdated file → ⚠️ stale; mid-run kill → old file stays stale

---

## 7. Phase 4 — DR-0001 BM25 Search In Dashboard

**Goal:** real search with synonym expansion replaces `txt.includes(q)`.

### Tasks
- **P4.1** `search/corpus.py` — serialize article corpus (id/title/desc/excerpt/keywords/source)
  + embed `synonym_map.json` as `<script type="application/json">` blocks in `index.html`.
- **P4.2** `render/news.py` + `render/gateway.py` — inject the two JSON blocks.
- **P4.3** Dashboard JS — upgrade `applyFilters()`: expand query via synonym map, weighted
  term-frequency score (title > excerpt), filter by ≥1 expanded-term match. Combine with
  existing source/category filters.

### Verification
- [ ] "KPK" finds "Komisi Pemberantasan Korupsi" articles
- [ ] "economy" finds Indonesian "ekonomi" articles
- [ ] source/category filters still work in combination; empty state still shows

---

## 8. Phase 5 — DR-0005 Entity Layer

**Goal:** entities extracted, alias-resolved, wikilinked into .md, entity pages generated.
Co-occurrence tracked. **Note the DR-0012 §6 first-appearance guard is implemented HERE.**

**DDL (into migrate.py):** `entities`, `article_entities`, `entity_cooccurrence`.

### Tasks
- **P5.1** `enrich/entities.py` (CODE) — regex+seed+gazetteer NER → RawEntity list. Seed from
  `synonym_map.json`. Test precision/recall on a labeled fixture of ~20 articles.
- **P5.2** `enrich/entity_linker.py` (CODE) — resolve aliases → canonical; create new entities;
  **apply DR-0012 §6 guard** (`is_genuine_new_entity`: extraction-confidence + rapidfuzz ≥88
  alias check) so ⚡ first-appearance doesn't fire on noise. Update `entity_cooccurrence`.
- **P5.3** `enrich/tagger.py` (CODE) — rewrite article .md: first mention per entity →
  `[[Canonical|surface]]`; never inside frontmatter/code/existing links.
- **P5.4** Entity page renderer — `entities/{type}/{slug}.md`, regenerated each run from DB.
- **P5.5** Entity brief builder (compressed form for the writer) with `⚡ FIRST APPEARANCE`
  + `⚠ NEW CO-OCCURRENCE` flags — the latter gated by DR-0012 §3 nPMI (implemented in P6's
  `signal/pmi.py`; until P6 exists, brief emits the flag unguarded behind a feature switch).

### Verification
- [ ] Article .md gains `[[canonical|surface]]` wikilinks after tagger
- [ ] `entities/persons/prabowo-subianto.md` exists with connected entities
- [ ] A misspelling of a known entity (fuzz ≥88) does NOT mint a new entity / ⚡ flag

---

## 9. Phase 6 — DR-0006 Signal Layer + DR-0012 Provenance-Aware Scoring

**Goal:** detect same-event clusters, group provenance, score with the HONEST confidence
model, write signal .md. **Build DR-0012's scorer directly — never the naive DR-0006 one.**

**Specs:** `DR-0006` (clustering + signal pages) and `DR-0012` (provenance, scoring, PMI,
contradiction, lineage). **DDL:** `provenance_groups`, `clusters` (+ lineage cols),
`signals`; ALTER `articles` (+ wire_origin, provenance_group, is_originator, minhash_sig).

### Atomic tasks (ORDER MATTERS — provenance precedes scoring)
- **P6.1** `signal/provenance.py` (CODE) — wire-dateline extraction (WIRE_AGENCIES whitelist),
  MinHash-LSH candidate gen + **exact** shingle-Jaccard verify, union-find groups, originator
  pick, cross-day grouping via stored `minhash_sig`. Tests: verbatim dup grouped; self-brand
  not treated as wire; Day-2 reprint joins Day-1 originator.
- **P6.2** `signal/cluster.py` (CODE+, REVISED) — entity-overlap (≥0.4) + BM25 (≥0.35) →
  clusters; **lineage assignment** (≥0.5 entity Jaccard vs recent 3d → same `lineage_id`).
  Test: developing story keeps one lineage across two days.
- **P6.3** `signal/contradiction.py` (CODE) — numeric-claim extraction with id-locale money
  normalization (`parse_id_number` + `UNIT_MULT`), monotonic-toll guard, returns
  `(bool, list, consistency_float)`. Tests: 2,3T vs 5T → contested; 2,3 triliun vs 2.300
  miliar → not contested; rising toll → not contested.
- **P6.4** `signal/pmi.py` (CODE) — nPMI with `MIN_ENTITY_CT=5`, `MIN_COOCCUR=3` floors;
  `is_meaningful_cooccurrence`. Test: surprising pair ranks above prominence pair.
- **P6.5** `signal/scorer.py` (CODE, DR-0012) — `effective_sources` (soft-reprint 0.5
  down-weight), confidence formula, 5-state `classify()` incl. domestic-corroboration
  CONFIRMED path + SINGLE_SOURCE_AMPLIFIED. Tests: the full DR-0012 verification matrix.
- **P6.6** `signal/gateway.py` (GATEWAY) — order: provenance → cluster → contradiction → pmi
  → scorer → write `signals/YYYY-MM-DD/*.md`. Idempotent; caches `cluster.consistency`.

### Gates
- [ ] Wire story reprinted 3× → `effective_sources ≈ 1` → SINGLE_SOURCE_AMPLIFIED (not CONFIRMED)
- [ ] 3 independent domestic originals → CONFIRMED
- [ ] All 18 DR-0012 verification checkboxes pass
- [ ] `nd_scan` clean; provenance provably runs before scorer (gateway-enforced order)

---

## 10. Phase 7 — DR-0007 Hermes Writer

**Goal:** graph-aware analytical article per signal; review gate; wikilinked output.

**Spec:** `DR-0007` + DR-0012 §7 (review gate) + DR-0012 lineage identity rules.
**DDL:** `hermes_articles` (+ `publish_state`). **LLM:** Claude **Haiku 4.5**
(`claude-haiku-4-5-20251001`); fallback opencode minimax-free if no API key.

### Tasks
- **P7.1** `signal/brief.py` (CODE) — assemble WriterContext: signal + compressed entity
  briefs (with ⚡/⚠ flags + nPMI) + cluster article full text + prior-day body for lineage
  continuations.
- **P7.2** `signal/writer.py` (CODE) — eight-block prompt (incl. hardened GATE_AWARENESS:
  nPMI≥0.30 to assert links, SINGLE_SOURCE_AMPLIFIED disclosure, no causal claims from
  co-occurrence). One LLM call per signal. UPSERT on `hrm-{lineage_id}` (no dupes).
- **P7.3** Review gate (`publish_state`): CONFIRMED/REPORTED + high-confidence EMERGING →
  `published`; SINGLE_SOURCE_AMPLIFIED/CONTESTED/low-EMERGING → `pending_review`.
- **P7.4** Write `hermes/YYYY-MM-DD/{lineage}.md` with byline + epistemic footer.

### Verification
- [ ] EMERGING articles use hedged language; CONFIRMED state facts directly
- [ ] SINGLE_SOURCE_AMPLIFIED article → `pending_review`, states "single origin" explicitly
- [ ] Low-nPMI pair → writer does not assert a relationship
- [ ] Re-run does not duplicate Hermes articles (UPSERT on lineage); cost <$0.01 for ≤20 signals

---

## 11. Phase 8 — DESIGN UI (Briefing + Epistemic System + Rail)

**Goal:** the signal-first redesign. **Spec:** `docs/DESIGN.md` (Parts 3–7), revises DR-0008.

### Tasks
- **P8.1** Epistemic visual tokens (`--confirmed/--reported/--amplified/--emerging/--contested`)
  + pill components. The 5-state palette from DESIGN.md Part 5 — `↻ 1 origin` marker for
  amplified, confidence bar for emerging only.
- **P8.2** Command-bar + ⌘K search (promote DR-0001 search to command bar) + **Review badge**
  (pending_review count → approve/discard queue).
- **P8.3** `render/briefing.py` (CODE, NEW) — significance-ranked Hermes homepage
  (lead/secondary/tertiary sizing). Becomes default mode.
- **P8.4** Mode switch `[Briefing][Feed][Graph][Entities]`; Feed = current grid + cluster-status
  tints + "in cluster" chips; Football demoted to a Feed category.
- **P8.5** Hermes ticker rail (DESIGN.md Part 6 option C) — ambient auto-advance on non-Briefing
  modes; pause-on-hover. (This is the revised, demoted DR-0008.)

### Verification
- [ ] All 5 epistemic states render with correct color + markers
- [ ] Briefing is default; significance ranking visible (lead card largest)
- [ ] Review badge shows pending_review count; approve moves item to published
- [ ] Feed cluster tints + "in cluster" chips link to the Hermes analysis

---

## 12. Phase 9 — DESIGN Graph & Entities (DR-0009/0010/0011, optional for MVP)

**Goal:** promote the knowledge graph and entity profiles to first-class modes.
**Spec:** `docs/DESIGN.md` Parts 4.3–4.4. Lower priority — ship P0–P8 first.

- **P9.1** GRAPH mode — full-screen vis.js (node size = article_count, edge = co-occurrence,
  ⚡ pulse on new), type/cluster filters, optional time-scrubber.
- **P9.2** ENTITIES mode — searchable directory + profile (connected entities, mention
  sparkline, recent articles, Hermes analyses the entity appears in).

---

## 13. Master Target File Tree (end state)

```
scripts/
  migrate.py            CODE   idempotent DDL runner
  database.py           CODE   DAL (unchanged)
  health.py             CODE   last_run.json writer
  sources/gateway.py    GATE   config.yaml → dispatch rss/football
  fetch/
    rss.py              CODE   RSS → stubs
    football.py         CODE   TheRundown API
    extractor.py        CODE   trafilatura text+images
    web_fetcher.py      CODE   opencode fallback
    extract_gateway.py  GATE   iterate → extract → persist
  enrich/
    taxonomy.py         CODE   canonical SECTION_KEYWORDS
    metadata.py         CODE   full-text enrichment
    auto.py             CODE   title/desc enrichment
    entities.py         CODE   NER
    entity_linker.py    CODE   alias resolve + first-appearance guard
    tagger.py           CODE   wikilink rewrite
  search/
    indexer.py          CODE   BM25 build
    query.py            CODE   BM25 query
    corpus.py           CODE   dashboard corpus JSON
  signal/
    provenance.py       CODE   wire dateline + near-dup grouping
    cluster.py          CODE   clustering + lineage
    contradiction.py    CODE   numeric-claim contradiction
    pmi.py              CODE   nPMI significance
    scorer.py           CODE   provenance-aware confidence (DR-0012)
    brief.py            CODE   writer context assembly
    writer.py           CODE   Hermes LLM article + review gate
    gateway.py          GATE   signal pipeline order
  render/
    news.py             CODE   feed cards
    football.py         CODE   football tab
    article.py          CODE   article viewer + graph data
    briefing.py         CODE   significance-ranked Hermes homepage
    health_badge.py     CODE   run-health badge
    gateway.py          GATE   MERGE + assemble index.html/article.html
run.sh                  TRIG   sources→extract→enrich→signal→search→render→health
config.yaml             data   authoritative source list
news/ entities/ signals/ hermes/   .md outputs (Obsidian)
data/   *.pkl, synonym_map.json, last_run.json
tests/  pytest suite + fixtures
```

---

## 14. Risk & Rollback

- **Cron breakage during P1.** Mitigation: shims keep old pipeline alive until each domain is
  green; flip `run.sh` last. If a run fails, `last_run.json` (P3) won't update → stale badge
  signals it.
- **LLM cost runaway (P7).** Cap signals per run; Haiku at ~$0.0003/article. Alert if a run
  exceeds N calls. Fallback to opencode-free if no key.
- **Provenance false-merges (P6).** Exact-Jaccard verify prevents over-grouping; soft-weight
  is conservative (0.5, not 0). If a real story is wrongly merged, lineage overlap threshold
  (0.5) is the tuning knob.
- **Entity-extraction noise (P5).** The first-appearance guard (fuzz ≥88 + extraction
  confidence) is the safety net; tune `ALIAS_SIMILARITY` if false-new entities appear.

---

## 15. Open Questions Carried From Prior Sessions

1. UI auto-scroll: Briefing-first (A) / rail (B) / hybrid (C) — DESIGN.md recommends **C**.
2. Default mode: Briefing vs Feed (recommend Briefing).
3. Football: Feed category (proposed) vs top-level mode.
4. Retention policy for `news/ entities/ signals/ hermes/` .md files.
5. Claude API key provisioning for P7 (else opencode-free fallback).
6. Source-tier list (DR-0012 `SOURCE_TIER`) — confirm tiers with Judah before P6.
```
