# Datagateway — Session Log

## Session: persona-brainstorm-20260627-001

Date: 2026-06-27
Personas: Ezekiel (dev), Jeremiah (product), Megumi (scribe)

---

## G-Q1: Why is BM25 rebuilt every run but never used in the dashboard?

- **Source:** temp-KB contradiction — search-index.py (step 8), applyFilters() in build-dashboard.py
- **Status:** DR-0001
- **Answer:** Judah built BM25 with synonym expansion because substring search fails on
  Indonesian abbreviations and bilingual queries. The index works but has no bridge to the
  UI — no HTTP endpoint, no JS integration. Dashboard search remains a naive `includes(q)`.
- **Closed:** 2026-06-27

---

## G-Q2: If Judah wants to add a new source, what does he edit?

- **Source:** temp-KB contradiction — config.yaml (8 sources) vs fetch-news.py SOURCES (13 entries)
- **Status:** DR-0002
- **Answer:** He must edit fetch-news.py SOURCES list directly. config.yaml is never read.
  Editing config.yaml has no effect. The two files have been diverging.
- **Closed:** 2026-06-27

---

## G-Q3: Can Judah tell from the dashboard whether the last run completed successfully?

- **Source:** temp-KB gap — set -euo pipefail, step-4 partial build, `last_update` timestamp
- **Status:** DR-0003
- **Answer:** No. Step-4 partial builds are indistinguishable from complete runs. The header
  timestamp is `datetime.now()` at build time — a partial build at step 4 shows a recent
  timestamp while having no scraped content or metadata. No run health indicator exists.
- **Closed:** 2026-06-27

---

## Decision Records Written

| ID | Title |
|---|---|
| DR-0001 | Wire BM25 Search Into Dashboard |
| DR-0002 | Make config.yaml the Authoritative Source List |
| DR-0003 | Run Health Indicator in Dashboard |
