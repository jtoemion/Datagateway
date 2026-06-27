# Session Handoff — persona-brainstorm-20260627-001

Date: 2026-06-27
Status: CLOSED — 3 decision records written

## What Was Done

- Context amortization: `PRD.md` written at repo root (full architecture, sources,
  what works, contradictions, open questions)
- Jeremiah KB generated: `persona-brainstorm/jeremiah-kb.md`
- 3 decision records written (cap reached):

| DR | Title | Files to Touch |
|---|---|---|
| DR-0001 | Wire BM25 Search Into Dashboard | `search/corpus.py`, `render/gateway.py`, `render/news.py` |
| DR-0002 | Make config.yaml Authoritative | `sources/gateway.py`, `fetch/rss.py`, `config.yaml` |
| DR-0003 | Run Health Indicator | `health.py`, `render/health_badge.py`, `run.sh` |
| DR-0004 | Node-Discipline Restructure (foundation) | All of `scripts/` → domain packages |
| DR-0005 | Entity Layer | NER, alias resolution, wikilink tagging, entity .md pages |
| DR-0006 | Signal Layer | Clustering, epistemic scoring, signal .md pages |
| DR-0007 | Hermes Writer | Graph-aware AI analysis from signal + entity context |
| DR-0008 | Left Column Carousel | 280px sticky panel, step-and-hold auto-scroll (revise per DESIGN.md) |
| DR-0012 | Provenance-Aware Confidence | near-dup grouping, independent-source counting, PMI gate, contradiction detection, review gate — **build before trusting any confidence output** |

## Runtime Context

Datagateway runs inside **Hermes agent**. Node-discipline (TRIGGER/CODE/GATEWAY) applies
to all implementation. See PRD.md § "Node Architecture (Target)" for full node map and
current violations.

## Next Agent Pick-Up

**START HERE: `PLAN.md`** — the master implementation plan. It sequences every DR into
atomic, dependency-ordered phases (P0–P9) with node-discipline + TDD gates and per-phase
verification. Then read `PRD.md` (context), `docs/DESIGN.md` (UI), and the DRs it references.

Key instruction from PLAN.md: build DR-0006 + DR-0012 as ONE phase (P6) — implement the
provenance-aware scorer directly; never ship the naive confidence model.

**Implement in order:**
1. DR-0004 — node-discipline restructure (structural foundation; all others depend on it)
   - `scrape-article.py` + `backfill-images.py` DELETED; replaced by `fetch/extractor.py`
   - `trafilatura` installed (`pip install trafilatura --break-system-packages`)
   - Benchmark: Antara 320w/0.1s, BBC 886w/0.1s, CNN Indonesia 404w/0.2s
   - `opencode web_fetch` fallback only (word_count < 150 or None)
   - Image extraction: hero from `meta.image`, body from XML `<graphic>` tags
   - Body image filter: skip empty-alt, skip logo/icon/banner URLs, dedup, cap 8
   - Full extractor spec in DR-0004 § What to Build → fetch/extractor.py
2. DR-0002 — config.yaml → `sources/gateway.py` (smallest, unblocks source management)
3. DR-0003 — run health → `health.py` + `render/health_badge.py` (standalone)
4. DR-0001 — BM25 search → `search/corpus.py` + upgrade `render/news.py` JS (largest)

## Remaining Open Questions

4. Retention policy for `news/`, `entities/`, `signals/`, `hermes/` .md files?
5. Claude API key setup for DR-0007 writer (Haiku 4.5 recommended; minimax-free fallback)
(Q "merge SECTION_KEYWORDS" resolved by DR-0004 → `enrich/taxonomy.py`)
