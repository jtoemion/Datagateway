# DR-0005: Entity Layer — NER, Wikilinks, Entity Pages

Date: 2026-06-27
Status: Accepted
Session: persona-brainstorm-20260627-001 (addendum)
Node location: `enrich/entities.py`, `enrich/entity_linker.py`, `enrich/tagger.py`
Depends on: DR-0004 (node-discipline restructure)

## Context

Articles currently have a flat `entities_json` list in `article_metadata`. Entities are
not resolved across articles (same person appears as "Prabowo", "Presiden Prabowo",
"Prabowo Subianto"), not linked between articles, and not tracked over time.
The wikilink on each article today is a single `[[slug]]` for the article itself —
not for the entities within it.

The entity layer is the analytical substrate that makes signal synthesis sharp.
Without it, the writer sees only today's articles. With it, the writer sees
"KPK has appeared in 31 articles since May, co-appearing with Prabowo 23 times —
and Dana Haji appears for the first time today."

## Decision

Entities become first-class nodes. Every entity gets a canonical form, an entity page
(.md), and a SQLite record. Every article .md gets entity mentions replaced with
`[[Canonical Name|display text]]` wikilinks. Entity pages are updated every run.

## New DB Tables

```sql
CREATE TABLE entities (
    id           TEXT PRIMARY KEY,          -- ent-{hash of canonical_name}
    canonical    TEXT NOT NULL UNIQUE,      -- "Prabowo Subianto"
    type         TEXT NOT NULL,             -- PERSON | ORG | PLACE | CONCEPT | EVENT
    aliases_json TEXT DEFAULT '[]',         -- ["Prabowo", "Presiden Prabowo", "Menhan"]
    first_seen   TEXT NOT NULL,
    last_seen    TEXT NOT NULL,
    article_count INTEGER DEFAULT 0
);

CREATE TABLE article_entities (
    article_id    TEXT NOT NULL REFERENCES articles(id),
    entity_id     TEXT NOT NULL REFERENCES entities(id),
    mention_count INTEGER DEFAULT 1,
    PRIMARY KEY (article_id, entity_id)
);

CREATE TABLE entity_cooccurrence (
    entity_a     TEXT NOT NULL REFERENCES entities(id),
    entity_b     TEXT NOT NULL REFERENCES entities(id),
    co_count     INTEGER DEFAULT 1,
    last_seen    TEXT NOT NULL,
    PRIMARY KEY (entity_a, entity_b)
);
```

## What to Build (v1)

### `enrich/entities.py` (CODE)
Input: article full_text + title + description
Output: list of RawEntity(surface_form, type, start_pos, end_pos)

Extraction approach (no LLM, offline):
- PERSON: regex patterns for Indonesian/international names + title prefixes
  (Presiden, Menteri, Jenderal, Dr., Prof., Senator, PM, President)
- ORG: uppercase acronyms (KPK, DPR, TNI, BNN) + known org suffix patterns
  (PT, Tbk, Kementerian, Partai, Bank, Universitas)
- PLACE: country/city names from a static gazetteer (capitals + Indonesian cities)
- CONCEPT: domain terms from taxonomy.py section keywords (reuse)
- Seed list from `synonym_map.json` (already has canonical forms)

### `enrich/entity_linker.py` (CODE)
Input: list of RawEntity (surface forms)
Output: list of LinkedEntity(entity_id, canonical, type, aliases)

Resolution:
1. Exact match against `entities.canonical`
2. Alias match against `entities.aliases_json`
3. Synonym map lookup (synonym_map.json has Prabowo → Prabowo Subianto)
4. If no match → create new entity record (canonical = surface form, type = detected)
5. Update `entity_cooccurrence` for all pairs in the article

### `enrich/tagger.py` (CODE)
Input: article .md text + list of LinkedEntity with positions
Output: .md text with entity spans replaced by wikilinks

Rules:
- Replace first occurrence per entity per article: `Presiden Prabowo` → `[[Prabowo Subianto|Presiden Prabowo]]`
- Subsequent occurrences: leave as-is (don't over-link)
- Never link inside code blocks, frontmatter, or existing `[[...]]` spans
- Write updated .md back to news/YYYY-MM-DD/{slug}.md

## Entity Page Format

File: `entities/{type-folder}/{slug}.md`
Example: `entities/persons/prabowo-subianto.md`

```markdown
---
entity_id: ent-abc123
canonical: Prabowo Subianto
type: PERSON
aliases: [Prabowo, Presiden Prabowo, Prabowo Subianto, Menhan]
first_seen: 2026-05-01
last_seen: 2026-06-27
article_count: 47
---

# Prabowo Subianto

## Recent Articles (last 14 days)
- 2026-06-27 · [[antara_susunan-pemain-uruguay]] — Prabowo hadiri KTT ASEAN
- 2026-06-25 · [[cnn_indonesia_defense-summit]] — Indonesia-Malaysia defense pact
- 2026-06-20 · [[detik_cabinet-reshuffle]] — Kabinet Merah Putih reshuffle rumors

## Connected Entities
- [[KPK]] — 23 co-mentions
- [[Joko Widodo]] — 18 co-mentions
- [[Kabinet Merah Putih]] — 15 co-mentions
- [[DPR]] — 11 co-mentions
```

Entity pages are fully regenerated every run (not incremental) — they always reflect
current DB state. Fast: one SQL query per entity.

## Entity Brief Format (for DR-0007 writer context)

Compressed form injected into writer prompt — NOT the full entity page:

```
[ENTITY BRIEF]
Prabowo Subianto (PERSON) — 47 mentions, active since 2026-05-01
  Recent contexts: KTT ASEAN (2026-06-27), defense pact (2026-06-25), cabinet rumors (2026-06-20)
  Co-appears with: KPK (23x), Joko Widodo (18x), Kabinet Merah Putih (15x)

KPK (ORG) — 31 mentions, active since 2026-05-01
  Recent contexts: Kemenag probe (2026-06-26), OTT Jakarta (2026-06-22)
  Co-appears with: Prabowo Subianto (23x), DPR (12x)

Dana Haji (CONCEPT) — 1 mention — ⚡ FIRST APPEARANCE TODAY
```

The `⚡ FIRST APPEARANCE TODAY` flag is the key signal for the writer — a new entity
entering the graph is analytically significant. So is a known entity appearing in a
new co-occurrence pairing for the first time.

## What Is Deliberately Excluded

- No ML-based NER (spaCy, transformers) — regex + seed list is sufficient for v1
- No cross-language entity linking (Indonesian "Presiden" ≠ resolved to English "President")
- No entity disambiguation beyond alias matching (two people named "Ahmad" stay separate)
- No entity page summaries (just recent articles + co-entities — summaries come in DR-0007)

## Files Deleted / Replaced

- No files deleted. This extends existing `enrich/` package.
- `backfill-images.py` already deleted in DR-0004.

## Verification

- [ ] `entities/` directory created with `persons/`, `orgs/`, `places/`, `concepts/` subdirs
- [ ] `entities` + `article_entities` + `entity_cooccurrence` tables exist in DB
- [ ] `python3 -c "from scripts.enrich.entities import extract_entities"` works
- [ ] Antara article .md contains at least one `[[canonical|surface]]` wikilink after tagger runs
- [ ] `entities/persons/prabowo-subianto.md` exists after run (if Prabowo mentioned in any article)
- [ ] Entity co-occurrence table populated: KPK + Prabowo appear together in at least N rows
- [ ] `⚡ FIRST APPEARANCE TODAY` flag appears in entity brief for a newly seen entity
