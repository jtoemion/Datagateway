# DR-0012: Provenance-Aware Confidence Model

Date: 2026-06-27
Status: Accepted
Session: persona-brainstorm-20260627-001 (tradecraft hardening)
Node location: `signal/provenance.py`, `signal/pmi.py`, `signal/contradiction.py`,
               revisions to `signal/cluster.py`, `signal/scorer.py`, `signal/brief.py`,
               `signal/writer.py`, `enrich/entity_linker.py`
Depends on: DR-0005 (entity layer), DR-0006 (signal layer — this revises its scoring),
            DR-0007 (Hermes writer — this adds guards)
Supersedes: DR-0006 §scorer.py confidence model, DR-0007 §auto-publish behavior

## Context

DR-0006's confidence model treats every article as an independent source. It is not.
Indonesian media massively republishes wire copy — Antara (state agency), Reuters, and AP
items are reprinted with light edits across CNN Indonesia, Detik, CNBC Indonesia,
Republika, and others. Under DR-0006, one wire story reprinted by 3 outlets scores
CONFIRMED. That **inverts** the corroboration logic: heavy republication of a single
origin is the opposite of independent confirmation. It is the textbook OSINT echo-chamber
failure.

Three coupled defects follow:

1. **Circular reporting inflates confidence** (no provenance / near-dup detection).
2. **The Hermes writer manufactures insight from coincidence** — co-occurrence frequency is
   handed to the LLM as "significance," but two prominent entities co-occur often merely
   because both are prominent. Auto-published with no review gate (DR-0007).
3. **Fragile signals**: `⚡ first appearance` fires on extraction noise (a regex finally
   catching a spelling variant), and CONTESTED has no machinery to detect contradiction.

This DR makes the intelligence flow trustworthy rather than confidently wrong.

## Decision

Introduce **provenance grouping** so independent sources are counted correctly, rework the
confidence model around independent origins, gate analytical significance on **PMI** (not
raw frequency), add **numeric-claim contradiction detection** so CONTESTED is real, give
clusters **cross-day lineage** for story continuity, and add a **review gate** so
low-confidence synthesis never auto-publishes.

---

## Subsystem 1 — Provenance Grouping (`signal/provenance.py`, CODE)

Collapse reprints of the same underlying report into one **provenance group** before any
source counting happens. Identify the originating source.

### Inputs
Articles in a clustering window with `full_text`, `source`, `date`, `url`.

### Step 1 — Dateline / wire attribution extraction
Indonesian and international wire copy carries explicit datelines and attributions.
These are the strongest provenance signal — stronger than timestamps.

**Critical distinction (bug fixed in review):** a dateline parenthetical can be a *wire
agency* (`Jakarta (ANTARA) -` → wire copy) OR an *outlet's own brand* (`JAKARTA, KOMPAS.com -`
→ first-party reporting, NOT a wire). Only the former is provenance evidence. Match the
captured token against a **wire-agency whitelist** — never treat an outlet self-brand as a wire.

```python
# Only these are genuine wire agencies whose attribution implies republished copy.
# An outlet's own brand in a dateline (KOMPAS.com, Detikcom) is self-attribution, NOT a wire.
WIRE_AGENCIES = {
    "ANTARA": "Antara", "REUTERS": "Reuters", "AP": "AP", "AFP": "AFP",
    "BLOOMBERG": "Bloomberg", "ASSOCIATED PRESS": "AP",
}   # extend in config, not code

DATELINE_PATTERNS = [
    # "Jakarta (ANTARA) -"  — token inside parens, validated against whitelist below
    re.compile(r'^\s*[A-Za-z .]{2,40}\(([A-Za-z ]{2,})\)\s*[-–—]'),
    # inline attribution: "ANTARA melaporkan", "Reuters reported"
    re.compile(r'\b([A-Za-z ]{2,})\b\s+(?:melaporkan|reported|reports)\b', re.I),
    # trailing credit: "Sumber: Reuters"  /  "(Antara)"
    re.compile(r'(?:Sumber|Source)\s*:\s*([A-Za-z ]{2,})', re.I),
]

def extract_wire_origin(text: str) -> str | None:
    head, tail = text[:400], text[-200:]   # datelines top, credits bottom
    for pat in DATELINE_PATTERNS:
        m = pat.search(head) or pat.search(tail)
        if m:
            token = m.group(1).strip().upper()
            if token in WIRE_AGENCIES:      # whitelist gate — self-brands fall through
                return WIRE_AGENCIES[token]
    return None
```

### Step 2 — Near-duplicate detection (MinHash LSH)
Verbatim and near-verbatim reprints share long passages. Use MinHash over word shingles.

```python
from datasketch import MinHash, MinHashLSH

SHINGLE_K       = 8        # 8-word shingles capture verbatim passages
NUM_PERM        = 256      # raised from 128 — at 128 the ±est. error straddles 0.50
DUP_JACCARD     = 0.50     # LSH candidate threshold (estimate); candidates re-verified
LSH_BAND        = 0.45     # slightly loose LSH band so true dups aren't pre-filtered out
                           # (conservative; verbatim wire copy lands ~0.7–0.95)

def shingles(text: str, k: int = SHINGLE_K) -> set[str]:
    toks = re.findall(r'\w+', text.lower())
    return {' '.join(toks[i:i+k]) for i in range(max(0, len(toks)-k+1))}

def build_minhash(text: str) -> MinHash:
    mh = MinHash(num_perm=NUM_PERM)
    for sh in shingles(text):
        mh.update(sh.encode())
    return mh

def find_reprint_groups(articles: list[Article]) -> list[list[str]]:
    lsh   = MinHashLSH(threshold=LSH_BAND, num_perm=NUM_PERM)   # loose: candidate gen only
    mhs   = {}
    shsets = {}
    for a in articles:
        sh = shingles(a.full_text)
        shsets[a.id] = sh
        mh = MinHash(num_perm=NUM_PERM)
        for s in sh:
            mh.update(s.encode())
        mhs[a.id] = mh
        lsh.insert(a.id, mh)
    uf = UnionFind([a.id for a in articles])
    for a in articles:
        for cand in lsh.query(mhs[a.id]):
            if cand == a.id:
                continue
            # VERIFY with EXACT Jaccard on shingle sets — not the MinHash estimate
            sa, sb = shsets[a.id], shsets[cand]
            exact = len(sa & sb) / max(len(sa | sb), 1)
            if exact >= DUP_JACCARD:
                uf.union(a.id, cand)
    return uf.groups()
```

LSH does cheap candidate generation; the union is gated on **exact** shingle Jaccard so the
threshold is real, not an estimate. At ~195 articles/run the exact check on LSH candidates
is sub-second. **Decision: `datasketch` MinHashLSH for candidates + exact verify** (scales
out as the cross-day corpus grows).

> **Known limit — lexical dedup misses paraphrase.** This catches *verbatim* and
> near-verbatim reprints. A large share of Indonesian republishing is *rewritten* from an
> Antara item (same facts, different sentences), which shares few 8-word shingles and will
> NOT be grouped — so it is counted as independent, partially re-opening the echo problem.
> v1 mitigation: the scorer applies a **soft-reprint down-weight** (Subsystem 2) when two
> articles in a cluster have high entity overlap + high BM25 similarity but no independent
> wire dateline — treated as 0.5 of an independent source, not a full one. True semantic
> dedup (embeddings) is deferred to v2 (same mechanism needed for cross-language).

### Step 3 — Assign originator within each group
```python
def pick_originator(group: list[Article]) -> Article:
    # published_at = parsed, tz-normalized datetime (NOT the raw RSS date string —
    # lexical comparison of mixed-format date strings is unsafe)
    wired = [a for a in group if a.wire_origin]
    if wired:
        # an outlet whose own source IS the wire it cites is the originator
        native = [a for a in wired if a.source.lower() == a.wire_origin.lower()]
        return native[0] if native else min(wired, key=lambda a: a.published_at)
    return min(group, key=lambda a: a.published_at)   # earliest publish time
```

### Output → DB
```sql
ALTER TABLE articles ADD COLUMN wire_origin        TEXT;       -- "Antara" | NULL
ALTER TABLE articles ADD COLUMN provenance_group   TEXT;       -- pg-{hash}
ALTER TABLE articles ADD COLUMN is_originator      INTEGER DEFAULT 0;
ALTER TABLE articles ADD COLUMN minhash_sig        BLOB;       -- pickled MinHash, reused
                                                               -- across days so a reprint
                                                               -- of an OLDER article is
                                                               -- detected without re-fetch
```

> **Cross-day reprints:** provenance grouping queries the prior 3 days of `articles` and
> includes their stored `minhash_sig` in the LSH index, so a Day-2 reprint of a Day-1 wire
> story is grouped with the Day-1 originator (which keeps `is_originator`). Without this, a
> story that breaks late on Day 1 and is reprinted Day 2 would falsely count as 2 origins.

```sql
CREATE TABLE provenance_groups (
    id              TEXT PRIMARY KEY,    -- pg-{hash}
    originator_id   TEXT REFERENCES articles(id),
    member_ids_json TEXT NOT NULL,
    wire_origin     TEXT,                -- detected agency or NULL
    member_count    INTEGER DEFAULT 1,
    first_seen      TEXT NOT NULL
);
```

**The rule that fixes everything downstream:** a provenance group counts as **one**
independent source, no matter how many outlets reprinted it.

---

## Subsystem 2 — Reworked Confidence Model (`signal/scorer.py`, REVISED)

Replace the DR-0006 formula. Count **independent provenance groups**, not articles or outlets.

```python
def score_cluster(cluster: Cluster, groups: dict, entities: dict) -> EpistemicScore:
    members      = cluster.article_ids
    indep_groups = distinct_provenance_groups(members, groups)
    raw_indep    = len(indep_groups)               # distinct provenance groups
    article_count = len(members)

    # SOFT-REPRINT DOWN-WEIGHT (covers paraphrased reprints lexical dedup missed):
    # a group with no independent wire dateline that is highly similar (entity+BM25)
    # to a more-authoritative group counts as 0.5, not 1.0.
    effective_sources = soft_weighted_source_count(indep_groups, groups, cluster)  # float
    independence_ratio = effective_sources / max(article_count, 1)

    # authority from ORIGINATORS only (downstream reprints add none)
    originator_tiers = [SOURCE_TIER.get(groups[g].wire_origin or groups[g].originator_source, 0.4)
                        for g in indep_groups]
    authority_score  = max(originator_tiers) if originator_tiers else 0.4

    consistency = fact_consistency(cluster)        # 0–1 float, defined in Subsystem 4

    corroboration = min(effective_sources / 3.0, 1.0)   # saturates at 3 independent origins
    confidence = round(corroboration*0.50 + authority_score*0.30 + consistency*0.20, 2)

    status = classify(effective_sources, article_count, authority_score, consistency, cluster)
    return EpistemicScore(status, confidence, independence_ratio,
                          effective_sources, raw_indep)


SOURCE_TIER = {            # originator authority, 0.0–1.0  (default 0.4)
    "Reuters": 1.0, "AP": 1.0, "AFP": 1.0, "BBC": 1.0, "Bloomberg": 0.95, "Antara": 0.9,
    "CNN Indonesia": 0.7, "CNBC Indonesia": 0.7, "The Guardian Football": 0.7,
    "Detik": 0.65, "Republika": 0.6, "Sky Sports Football": 0.6,
}
TIER1 = 0.9                # threshold for "primary outlet"
```

### Epistemic status — honest about echo AND about independent domestic corroboration

```python
def classify(eff_sources, article_count, authority, consistency, cluster) -> str:
    """eff_sources is the soft-weighted independent-source count (float)."""
    if cluster.has_numeric_contradiction:                       # Subsystem 4
        return "CONTESTED"

    # Echo case FIRST: widely run, but traces to a single origin.
    if eff_sources < 2 and article_count >= 4:
        return "SINGLE_SOURCE_AMPLIFIED"

    # Strong corroboration: ≥3 independent origins.
    #  - with a tier-1 originator AND consistent facts → CONFIRMED
    #  - three INDEPENDENT mid-tier domestic originals, consistent → also CONFIRMED
    #    (fixes the gap where domestic-only corroboration could never confirm)
    if eff_sources >= 3 and consistency >= 0.66:
        return "CONFIRMED"

    # Moderate corroboration: ≥2 independent origins, OR 1 primary outlet.
    if eff_sources >= 2 or authority >= TIER1:
        return "REPORTED"

    # Single, non-primary, not widely amplified.
    return "EMERGING"
```

`SINGLE_SOURCE_AMPLIFIED` = a story everyone is running that traces to **one** origin —
labeled honestly instead of mislabeled CONFIRMED (UI: amber + "↻ 1 origin" marker).
The `eff_sources >= 3` CONFIRMED path now works for **independent domestic corroboration**
(e.g. three outlets each doing original reporting), not only when a wire agency is present.

### Soft-reprint down-weight (catches paraphrased reprints)

```python
SOFT_REPRINT_ENTITY_J = 0.70   # entity-set Jaccard
SOFT_REPRINT_BM25     = 0.55   # normalized BM25 similarity
SOFT_WEIGHT           = 0.5    # a suspected paraphrase counts as half a source

def soft_weighted_source_count(indep_groups, groups, cluster) -> float:
    """Distinct provenance groups, but groups that look like paraphrased reprints of a
    MORE authoritative group (high entity overlap + high BM25, no own wire dateline)
    count as SOFT_WEIGHT instead of 1.0."""
    weights = {}
    for g in indep_groups:
        weights[g] = 1.0
    for g in indep_groups:
        if groups[g].wire_origin:            # has its own wire attribution → genuine
            continue
        for h in indep_groups:
            if h == g:
                continue
            more_authoritative = SOURCE_TIER.get(groups[h].originator_source, 0.4) >= \
                                 SOURCE_TIER.get(groups[g].originator_source, 0.4)
            if (more_authoritative
                    and entity_jaccard(groups[g], groups[h]) >= SOFT_REPRINT_ENTITY_J
                    and bm25_sim(groups[g], groups[h]) >= SOFT_REPRINT_BM25):
                weights[g] = SOFT_WEIGHT
                break
    return sum(weights.values())
```

This is the v1 mitigation for the lexical-dedup blind spot named in Subsystem 1: a rewrite
of an Antara story that shares its entities and substance but not its sentences no longer
counts as a full independent corroboration.

---

## Subsystem 3 — PMI-Gated Significance (`signal/pmi.py`, CODE)

Stop handing the writer raw co-occurrence counts as "significance." Two prominent entities
co-occur often because both are prominent. Use **Pointwise Mutual Information** to surface
*surprising* associations only.

```python
import math

def pmi(entity_a: str, entity_b: str, stats: EntityStats) -> float:
    N      = stats.total_articles
    p_a    = stats.article_count[a] / N
    p_b    = stats.article_count[b] / N
    p_ab   = stats.cooccurrence[(a, b)] / N
    if p_ab == 0:
        return float("-inf")
    return math.log(p_ab / (p_a * p_b))

# Normalized PMI ∈ [-1, 1] for thresholding
def npmi(a, b, stats) -> float:
    p_ab = stats.cooccurrence[(a, b)] / stats.total_articles
    if p_ab == 0:
        return -1.0
    return pmi(a, b, stats) / (-math.log(p_ab))

PMI_SURPRISING = 0.30   # nPMI ≥ 0.30 = meaningfully associated, not coincidental prominence
MIN_ENTITY_CT  = 5      # PMI is noise below this; both entities must be seen ≥5 times
MIN_COOCCUR    = 3      # the pair must co-occur ≥3 times before we trust the association
```

PMI is statistically meaningless at single-digit counts — one chance co-occurrence of two
rare entities yields a high score. The floors below (`MIN_ENTITY_CT`, `MIN_COOCCUR`) are the
guard; a count-discounted PMI variant is a v2 refinement.

### Guarded co-occurrence flag (revises DR-0005 `⚠ NEW CO-OCCURRENCE`)
```python
def is_meaningful_cooccurrence(a, b, stats) -> bool:
    first_time = stats.cooccurrence[(a, b)] == stats.cooccurrence_today[(a, b)]
    surprising = npmi(a, b, stats) >= PMI_SURPRISING
    enough_obs = (stats.article_count[a] >= MIN_ENTITY_CT
                  and stats.article_count[b] >= MIN_ENTITY_CT
                  and stats.cooccurrence[(a, b)] >= MIN_COOCCUR)
    return first_time and surprising and enough_obs
```

Note the tension this resolves: a brand-new pairing (`first_time`) cannot also have
co-occurred `MIN_COOCCUR` times historically — so `⚠ NEW CO-OCCURRENCE` fires only when two
already-established entities (each seen ≥5×) pair up **and that pairing repeats ≥3× within
the current window**, i.e. a real emerging association, not a one-off coincidence. A truly
first-and-only co-occurrence is surfaced separately as low-confidence and is **not** narrated
as significant by the writer.

The brief (Subsystem 5) passes nPMI to the writer so it can distinguish a meaningful new
link from coincidental prominence — and is instructed not to narrate low-nPMI pairs.

---

## Subsystem 4 — Numeric-Claim Contradiction (`signal/contradiction.py`, CODE)

Make CONTESTED detectable. Contradictions in news surface as conflicting **quantities** —
money, casualties, dates, counts. Extract and compare them across the cluster.

```python
CLAIM_PATTERNS = {
    "money":    re.compile(r'(?:Rp|US\$|\$)\s?([\d.,]+)\s?(triliun|miliar|juta|ribu|billion|million|thousand)?', re.I),
    "casualty": re.compile(r'(\d+)\s+(orang|tewas|korban|meninggal|people|killed|dead|injured|luka)', re.I),
    "count":    re.compile(r'(\d+)\s+(pelaku|tersangka|suspect|arrested|ditangkap)', re.I),
    "date":     re.compile(r'\b(\d{1,2})\s+(Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|September|Oktober|November|Desember)\s+(\d{4})\b'),
}

# id-locale: comma is the DECIMAL separator, period is the THOUSANDS separator.
# Normalize EVERYTHING to a base integer so 2,3 triliun == 2.300 miliar == 2_300_000_000_000.
UNIT_MULT = {
    "triliun": 1_000_000_000_000, "miliar": 1_000_000_000, "juta": 1_000_000, "ribu": 1_000,
    "billion": 1_000_000_000, "million": 1_000_000, "thousand": 1_000, "": 1,
}

def parse_id_number(s: str) -> float:
    s = s.strip().replace(".", "")      # drop thousands separators
    s = s.replace(",", ".")             # comma decimal -> dot decimal
    return float(s)

def normalize_claim(ctype: str, m: re.Match) -> tuple[str, float]:
    if ctype == "money":
        val  = parse_id_number(m.group(1))
        unit = (m.group(2) or "").lower()
        return ("money", val * UNIT_MULT.get(unit, 1))
    if ctype in ("casualty", "count"):
        return (ctype, float(m.group(1)))
    if ctype == "date":
        return ("date", _to_ordinal(m))          # comparable integer day
    return (ctype, m.group(0))

# Monotonic quantities legitimately RISE over time (death tolls). A later, higher value
# is an UPDATE, not a contradiction. Only flag when values diverge AND it's not a clean
# monotonic increase ordered by publish time.
MONOTONIC = {"casualty"}                # tolls climb; counts of suspects can too — be strict
SPREAD_TOL = 1.25                       # >25% divergence

def has_contradiction(cluster_articles) -> tuple[bool, list, float]:
    # gather (publish_time, value) per claim type, keyed by claim subtype where needed
    by_type = defaultdict(list)
    for a in sorted(cluster_articles, key=lambda x: x.published_at):
        for ctype, vals in extract_claims(a.full_text).items():
            for v in vals:
                by_type[ctype].append((a.published_at, a.id, v[1]))

    contradictions, comparable_types, contested_types = [], 0, 0
    for ctype, series in by_type.items():
        values = [v for _, _, v in series]
        if len(set(values)) <= 1:
            comparable_types += 1
            continue
        comparable_types += 1
        spread = max(values) / max(min(values), 1)
        if spread < SPREAD_TOL:
            continue
        if ctype in MONOTONIC and _is_monotonic_increase(series):
            continue                    # rising toll = update, not contradiction
        contradictions.append((ctype, series))
        contested_types += 1

    consistency = 1.0 - (contested_types / comparable_types) if comparable_types else 1.0
    return bool(contradictions), contradictions, round(consistency, 2)


def fact_consistency(cluster) -> float:
    """0–1 agreement across comparable numeric claims. 1.0 when nothing conflicts
    (or nothing comparable exists). Cached on the cluster by signal/gateway after the
    has_contradiction() call so the scorer doesn't recompute."""
    return cluster.consistency        # set by gateway: _, _, cluster.consistency = has_contradiction(...)
```

`has_contradiction` now returns the **continuous `consistency`** the scorer needs (bug fix:
it was referenced but undefined). It also no longer flags a **rising death toll** as a
contradiction — monotonic increases ordered by publish time are treated as story updates.

Only fires CONTESTED when **independent** sources disagree (reprints share the same number
by construction, so they can't contradict — another reason provenance grouping comes first).

---

## Subsystem 5 — Cluster Lineage / Story Continuity (`signal/cluster.py`, REVISED)

Replace `cluster_id = hash(entity set)` with **lineage tracking** so a developing story
keeps one identity across days even as its entity set grows.

```python
LINEAGE_OVERLAP = 0.50   # ≥50% entity Jaccard with a recent cluster = same story

def assign_lineage(new_cluster, recent_clusters_3d) -> str:
    best, best_j = None, 0.0
    for rc in recent_clusters_3d:
        j = jaccard(set(new_cluster.entity_ids), set(rc.entity_ids))
        if j > best_j:
            best, best_j = rc, j
    if best and best_j >= LINEAGE_OVERLAP:
        return best.lineage_id          # continuation — same story
    return f"lin-{new_hash()}"          # new story
```

```sql
ALTER TABLE clusters ADD COLUMN lineage_id  TEXT;     -- stable across days
ALTER TABLE clusters ADD COLUMN developing  INTEGER DEFAULT 0;  -- continuation flag
ALTER TABLE clusters ADD COLUMN day_index   INTEGER DEFAULT 0;  -- 0 = first day seen
```

The writer brief now includes prior-day analysis for the lineage → genuine continuity, which
is the whole point of the accumulated-knowledge thesis. "Day 3 of the Dana Haji
investigation" instead of a cold re-analysis each morning.

### Signal & Hermes-article identity under lineage (resolves DR-0007 `UNIQUE(signal_id)`)

A developing lineage must NOT spawn a fresh signal/article every day (that would duplicate
the story). Identity is keyed on the **lineage**, not the per-day cluster:

```
signals.id          = sig-{lineage_id}        # one signal per story, updated daily
hermes_articles.id  = hrm-{lineage_id}         # one Hermes article per story
```

- Day 0: signal + Hermes article created for the lineage.
- Day N (continuation): the SAME signal row is **updated** (`updated_at`, new `day_index`,
  appended `article_ids`, re-scored), and the Hermes article is **re-written** in place
  (UPSERT on `hrm-{lineage_id}`), with the prior body passed into the brief as context.
- `UNIQUE(signal_id)` in `hermes_articles` (DR-0007) holds because both keys derive from the
  stable `lineage_id`. A revision overwrites; it does not insert.

This keeps "one story = one evolving signal = one evolving analysis," with `day_index`
exposed in the UI as "Day N."

---

## Subsystem 6 — First-Appearance Guard (`enrich/entity_linker.py`, REVISED)

`⚡ FIRST APPEARANCE` must not fire on extraction noise. Two guards:

```python
from rapidfuzz import fuzz

ALIAS_SIMILARITY = 88   # ≥88 token_sort_ratio to an existing entity = likely alias miss

def is_genuine_new_entity(surface: str, etype: str, mentions_in_article: int,
                          existing_entities) -> bool:
    # Guard 1 — extraction confidence: needs a title prefix, gazetteer hit, or repetition
    confident = (
        mentions_in_article >= 2
        or had_title_prefix(surface)            # "Presiden X", "Menteri Y"
        or in_gazetteer(surface, etype)
    )
    # Guard 2 — not a near-match of a known entity (alias the synonym map missed)
    likely_alias = any(
        fuzz.token_sort_ratio(surface, e.canonical) >= ALIAS_SIMILARITY
        for e in existing_entities if e.type == etype
    )
    return confident and not likely_alias
```

Near-matches are routed to the alias-resolution path (added to the existing entity's
`aliases_json`) instead of minting a spurious new entity and a false ⚡ flag.

---

## Subsystem 7 — Writer Review Gate (`signal/writer.py`, REVISED)

Low-confidence synthesis must not auto-publish. Revises DR-0007's "no review gate."

```python
AUTO_PUBLISH = {"CONFIRMED", "REPORTED"}

def publish_state(score: EpistemicScore) -> str:
    if score.status in AUTO_PUBLISH:
        return "published"
    if score.status == "EMERGING" and score.confidence >= 0.65:
        return "published"          # high-confidence emerging is allowed
    return "pending_review"         # SINGLE_SOURCE_AMPLIFIED, CONTESTED, low EMERGING
```

```sql
ALTER TABLE hermes_articles ADD COLUMN publish_state TEXT DEFAULT 'pending_review';
                                       -- published | pending_review
```

UI (BRIEFING / rail) shows only `published`. A **Review queue** (small badge in the command
bar) lists `pending_review` items for one-click approve/discard. The human stays in the loop
exactly where the machine is least sure.

### Writer prompt hardening (append to DR-0007 GATE_AWARENESS block)
```
- Co-occurrence is only meaningful when nPMI ≥ 0.30; for pairs below that, do NOT
  assert a relationship — state co-appearance as incidental or omit it.
- If status is SINGLE_SOURCE_AMPLIFIED: state explicitly that the story is widely
  circulated but traces to a single origin and is not independently corroborated.
- Never present statistical co-occurrence as causal or intentional linkage.
- If a fact is contradicted across sources (provided in contested[]), present both
  values and attribute each; do not pick one.
```

---

## Pipeline Order (revised, inside run.sh)

```
sources/gateway → fetch/extract_gateway → enrich (entities, taxonomy, metadata)
  → signal/provenance      ← NEW: must run before clustering/scoring
  → signal/cluster         ← REVISED: lineage assignment
  → signal/contradiction   ← NEW: feeds scorer
  → signal/pmi             ← NEW: feeds brief
  → signal/scorer          ← REVISED: independent-source confidence
  → signal/gateway (writes signal .md)
  → signal/brief → signal/writer  ← REVISED: PMI guard + review gate
  → search → render/gateway → health
```

Provenance grouping is a hard precondition for scoring. The gateway enforces order.

---

## What Is Deliberately Excluded (v1)

- **Stance/framing modeling** (Republika vs Antara vs BBC editorial slant) — v2. This DR
  handles factual contradiction, not interpretive framing.
- **Cross-language reprint detection** (Indonesian translation of a Reuters item) — MinHash
  is lexical; translated reprints won't match. v2 needs embedding similarity.
- **Calibration loop** (did "emerging 71%" come true?) — needs outcome resolution tracking;
  separate future DR. Confidence remains a heuristic, now an honest one.
- **Social/Telegram collection** — collection aperture stays mainstream RSS; out of scope.

## Verification

- [ ] A wire story (Antara originator) reprinted by 3 outlets yields `effective_sources ≈ 1`
- [ ] That same cluster classifies as `SINGLE_SOURCE_AMPLIFIED`, NOT `CONFIRMED`
- [ ] Three **independent domestic** originals (CNN Indonesia + Detik + Republika), consistent
      facts → `CONFIRMED` (the domestic-corroboration path, no wire agency required)
- [ ] A paraphrased rewrite of an Antara story (high entity+BM25 overlap, no own dateline)
      counts as `SOFT_WEIGHT` (0.5), not a full independent source
- [ ] `wire_origin` extracted from "Jakarta (ANTARA) -" but NOT from "JAKARTA, KOMPAS.com -"
      (outlet self-brand is not a wire)
- [ ] Two articles with verbatim shared passages land in the same `provenance_group`
      (exact shingle-Jaccard ≥ 0.50 on the LSH candidate, not the MinHash estimate)
- [ ] A Day-2 reprint of a Day-1 wire story groups with the Day-1 originator (cross-day)
- [ ] `fact_consistency` returns a 0–1 float and feeds both `confidence` and `classify`
- [ ] `npmi` ranks a surprising pair (KPK + niche entity) above a prominence pair (Prabowo + Jakarta)
- [ ] `⚠` new-co-occurrence fires only when both entities seen ≥5× and pairing repeats ≥3×
- [ ] A cluster with "Rp 2,3 triliun" vs "Rp 5 triliun" classifies as `CONTESTED`
- [ ] "Rp 2,3 triliun" vs "Rp 2.300 miliar" (same value, different unit) does NOT contradict
- [ ] A rising death toll ("3 tewas" → "7 tewas", ordered by publish time) does NOT contradict
- [ ] A developing story keeps one `lineage_id` and one `sig-{lineage_id}` across two run days;
      the Hermes article is UPSERTed, not duplicated
- [ ] A spurious entity (regex catching a known entity's misspelling, fuzz ≥ 88) does NOT get a ⚡
- [ ] A `SINGLE_SOURCE_AMPLIFIED` Hermes article lands in `pending_review`, not `published`
- [ ] Writer output for a low-nPMI pair does not assert a relationship between the entities

---

## Review Changelog (2026-06-27, second pass)

Fixes applied after a second critical review of this DR:

| # | Issue | Fix |
|---|---|---|
| 1 | `classify()` gap: 3 independent mid-tier domestic sources fell through to EMERGING | CONFIRMED path now `eff_sources ≥ 3 AND consistency ≥ 0.66` (tier-independent); REPORTED now `≥2 OR primary` |
| 2 | `consistency` used but never defined | `has_contradiction()` returns a 0–1 `consistency`; `fact_consistency()` reads the cached value |
| 3 | Dateline matched outlet self-brands as wires | `WIRE_AGENCIES` whitelist gate; self-brands fall through |
| 4 | Lexical dedup misses paraphrase | Stated as a known limit + `soft_weighted_source_count()` 0.5 down-weight mitigation |
| 5 | Rising death toll flagged as contradiction | Monotonic-increase guard ordered by publish time |
| 6 | Money normalization hand-waved | `parse_id_number` (comma-decimal) + `UNIT_MULT` harmonization specified |
| 7 | PMI unstable at low counts | `MIN_ENTITY_CT = 5`, `MIN_COOCCUR = 3` floors |
| 8 | MinHash estimate used as threshold | LSH for candidates, **exact** shingle-Jaccard to verify; `num_perm` 128→256 |
| 9 | Dangling `simhash` column | Replaced with `minhash_sig BLOB`, wired to cross-day reprint grouping |
| 10 | DESIGN.md out of sync | 5th state + `↻ 1 origin` marker + review-queue affordance added |
| 11 | Lineage ↔ `UNIQUE(signal_id)` unspecified | Identity keyed on `lineage_id`; daily continuation UPSERTs, not inserts |
```
