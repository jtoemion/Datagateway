# DR-0006: Signal Layer — Clustering, Epistemic Scoring, Signal Pages

Date: 2026-06-27
Status: Accepted
Session: persona-brainstorm-20260627-001 (addendum)
Node location: `signal/cluster.py`, `signal/scorer.py`, `signal/gateway.py`
Depends on: DR-0005 (entity layer — entity overlap drives clustering)

## Context

Multiple sources reporting the same event is currently invisible in Datagateway.
15 articles from Antara + CNN Indonesia + BBC about the same US-Iran strike appear as
15 separate unrelated cards. There is no mechanism to detect they're the same story,
no synthesis of what's confirmed vs. contested, and no epistemic status attached.

Entity layer (DR-0005) makes clustering tractable: two articles sharing ≥2 canonical
entities published within 24h are strong candidates for the same cluster. BM25 similarity
confirms it. Together they produce reliable same-event groupings.

## Decision

Detect same-event article clusters using entity overlap + BM25 similarity.
Score each cluster with an epistemic status and confidence value.
Write one Signal .md per cluster — structured, not prose (prose comes in DR-0007).

## New DB Tables

```sql
CREATE TABLE clusters (
    id              TEXT PRIMARY KEY,   -- clust-{hash}
    event_hash      TEXT NOT NULL,      -- hash of canonical entity set
    article_ids_json TEXT NOT NULL,     -- ["id1", "id2", "id3"]
    entity_ids_json  TEXT NOT NULL,     -- canonical entities shared across cluster
    source_count    INTEGER DEFAULT 1,
    first_seen      TEXT NOT NULL,
    last_updated    TEXT NOT NULL,
    epistemic_status TEXT DEFAULT 'emerging',  -- confirmed|reported|emerging|contested
    confidence      REAL DEFAULT 0.0
);

CREATE TABLE signals (
    id              TEXT PRIMARY KEY,   -- sig-{hash}
    cluster_id      TEXT NOT NULL REFERENCES clusters(id),
    core_facts_json TEXT DEFAULT '[]',  -- facts confirmed by ≥2 sources
    contested_json  TEXT DEFAULT '[]',  -- facts where sources disagree
    new_entities_json TEXT DEFAULT '[]',-- entities appearing for first time
    epistemic_status TEXT NOT NULL,
    confidence      REAL NOT NULL,
    lang            TEXT DEFAULT 'id',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
```

## What to Build (v1)

### `signal/cluster.py` (CODE)
Input: articles with entity lists (from article_entities table) + BM25 index
Output: list of Cluster(article_ids, shared_entities, source_count)

Algorithm:
```
1. Group articles published within same 24h window
2. For each pair in the window:
     entity_overlap = |entities_A ∩ entities_B| / min(|A|, |B|)
     if entity_overlap ≥ 0.4:  # share at least 40% of smaller set
         candidate cluster pair
3. BM25 similarity check on candidate pairs:
     sim = bm25_score(article_A.text, article_B.text)
     if sim ≥ 0.35: confirm cluster
4. Merge overlapping pairs into cluster groups (union-find)
5. Discard single-article "clusters" (no synthesis needed)
6. Persist to clusters table, update if cluster already exists
```

Cluster identity: `event_hash = hash(sorted canonical entity ids)`
Same event the next day (new articles added) updates the existing cluster.

### `signal/scorer.py` (CODE)
Input: Cluster + entity records
Output: EpistemicScore(status, confidence, core_facts, contested_facts, new_entities)

Epistemic status rules:
```
CONFIRMED:  source_count ≥ 3
            AND sources are independent (not same parent org)
            AND core fact set is consistent across ≥ 2/3 of sources

REPORTED:   source_count ∈ [1, 2]
            AND at least one is a primary outlet
            (primary outlets: Reuters, BBC, Antara, AP — add to config)

EMERGING:   source_count == 1
            OR source_count ≥ 2 but < 40% fact consistency

CONTESTED:  source_count ≥ 2
            AND core entities agreed
            BUT key facts directly contradict across sources
```

Confidence score (0.0–1.0, used inside EMERGING only):
```
source_diversity  = unique_sources / total_articles        (weight: 0.35)
source_authority  = avg(source_tier_score per article)     (weight: 0.35)
  tier 1 (1.0): Reuters, BBC, AP, Antara
  tier 2 (0.7): CNN Indonesia, CNBC Indonesia, Detik
  tier 3 (0.4): others
fact_consistency  = agreed_facts / total_facts_mentioned   (weight: 0.30)

confidence = (source_diversity × 0.35) + (source_authority × 0.35) + (fact_consistency × 0.30)
```

New entity detection:
```
for each entity in cluster:
    if entity.article_count == 1 and entity.first_seen == today:
        mark as ⚡ NEW ENTITY
```

### `signal/gateway.py` (GATEWAY)
Iterates articles → cluster.py → scorer.py → writes signal .md + updates DB.
Skips clusters already scored this run (idempotent).
Runs after `enrich/` step, before `signal/writer.py` (DR-0007).

## Signal Page Format

File: `signals/YYYY-MM-DD/{signal-id}.md`

```markdown
---
signal_id: sig-001
cluster_id: clust-xyz
epistemic_status: emerging
confidence: 0.71
source_count: 2
sources: [CNN Indonesia, Antara]
entities: [Prabowo Subianto, KPK, Dana Haji]
new_entities: [Dana Haji]
lang: id
created_at: 2026-06-27T07:15:00+07:00
---

# Signal: [auto-title from shared entity set + date]

## Epistemic Status
EMERGING — 2 sources, confidence: 71%
Reason: single-tier sources, fact consistency 68%

## Core Facts (agreed by ≥2 sources)
- KPK memanggil pejabat Kementerian Agama terkait pengelolaan Dana Haji
- Pemeriksaan dijadwalkan pada 2 Juli 2026

## Contested
- CNN Indonesia: dana yang dipermasalahkan Rp 2,3 triliun
- Antara: nilai belum dikonfirmasi, masih dalam penyelidikan awal

## New Entity Today
- ⚡ [[Dana Haji]] — muncul pertama kali, terkait pengelolaan investasi haji

## Entity Context
- [[KPK]] — 31 mentions · recent: OTT Jakarta (2026-06-22), Kemenag probe (2026-06-26)
- [[Prabowo Subianto]] — 47 mentions · co-appears with KPK 23x

## Source Articles
- [[cnn_indonesia_kpk-dana-haji-abc123]] — CNN Indonesia, 2026-06-27T06:30+07:00
- [[antara_kpk-kemenag-def456]] — Antara, 2026-06-27T07:00+07:00
```

## What Is Deliberately Excluded

- No cross-day cluster merging in v1 (same story over 3 days = 3 separate clusters)
  → Add in v2 once cluster identity is stable
- No fact extraction NLP (core_facts populated from title overlap heuristic in v1)
  → Full fact extraction needs LLM, add in DR-0007's writer context
- No source tier config UI — tier list hardcoded in scorer.py, editable manually
- No cluster visualization in the dashboard (vis.js graph already connects by date/category;
  cluster edges can be added in a later DR)

## Verification

- [ ] `clusters` + `signals` tables exist in DB after run
- [ ] Running pipeline on today's articles produces ≥1 cluster (US-Iran / FIFA WC coverage)
- [ ] `signals/2026-06-27/` directory contains at least one .md
- [ ] CONFIRMED cluster requires exactly ≥3 independent sources
- [ ] `⚡` new entity flag appears in signal .md for a first-seen entity
- [ ] Re-running pipeline does not duplicate clusters (idempotent)
