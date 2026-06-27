# DR-0007: Hermes Writer — AI Analysis from Graph Knowledge + Signal Context

Date: 2026-06-27
Status: Accepted
Session: persona-brainstorm-20260627-001 (addendum)
Node location: `signal/writer.py`, `signal/brief.py`
Depends on: DR-0006 (signal layer), DR-0005 (entity layer — entity briefs are the analytical substrate)

## Context

Signal pages (DR-0006) are structured data — confirmed facts, contested claims, entity
lists, epistemic scores. They are not readable analysis. What's missing is the
contextual reading: what does this event mean given everything we know about the
entities involved?

The entity layer (DR-0005) accumulates knowledge over time. By the time KPK appears
in a new cluster, Datagateway has seen KPK in 31 articles, knows its co-occurrence
patterns, knows who it's been investigating, and knows whether the current article's
entities have appeared with KPK before.

The writer's job: read the signal + the entity briefs + the raw cluster articles,
and produce a 300–500 word analytical article that a human analyst would be proud of.
Not a summary. An analysis — "what is actually happening."

## Decision

`signal/writer.py` assembles a writer context (signal + entity briefs + raw article text)
and calls an LLM (via opencode or Claude API) to produce a Hermes article.
The article is wikilink-tagged, epistemically calibrated, and stored in `hermes/`.

## What to Build (v1)

### `signal/brief.py` (CODE)
Input: signal_id
Output: WriterContext (structured string for LLM prompt)

Assembles from DB:
```
1. Signal metadata (epistemic_status, confidence, core_facts, contested, new_entities)
2. Entity brief for each entity in cluster (compressed — NOT full entity page):
     {canonical} ({type}) — {article_count} mentions since {first_seen}
     Recent contexts: {last 3 article titles} ({dates})
     Co-appears with: {top 5 co-entities} ({co_count}x each)
     [⚡ FIRST APPEARANCE TODAY] if new
     [⚠ NEW CO-OCCURRENCE: {entity_b}] if this pairing hasn't been seen before
3. Full text of each cluster article (truncated to 800 words each if needed)
4. Source tier info per article
```

The `⚡` and `⚠` flags are the analytical leverage points. A new entity or a new
pairing is almost always the "what's actually happening" signal.

### `signal/writer.py` (CODE)
Input: WriterContext
Output: HermesArticle(title, body, entities_used[], lang, epistemic_status, confidence)

LLM call — eight-block prompt (Hermes agent convention):

```
IDENTITY:
  hermes-writer — OSINT synthesis analyst for Datagateway

ROLE:
  Read the provided signal, entity briefs, and source articles.
  Write one analytical article that explains what is actually happening.
  You are not summarizing. You are analyzing.

PERSONA:
  Precise. Dense. No filler. Write like an analyst briefing a decision-maker.
  One paragraph of context, one paragraph of what happened, one paragraph of what it means.

GOAL:
  Produce a 300–500 word analytical article in {lang}.
  Exploit the entity graph: what is significant about WHO is involved,
  based on their history in the knowledge base?
  Flag new entities and new co-occurrences as analytically significant.

CONSTRAINTS:
  - CONFIRMED facts: state directly, no hedging
  - EMERGING/CONTESTED: use "diduga", "dilaporkan", "belum dikonfirmasi" (id)
    or "reportedly", "alleged", "unconfirmed" (en)
  - Do not invent details not present in source articles or entity briefs
  - Wikilink every entity on first mention: [[Canonical Name|display text]]
  - Do not start with "In this article" or "This analysis" or AI filler phrases
  - End with a one-sentence outlook: what to watch for next

OUTPUT_FORMAT:
  Title: <one punchy line, max 12 words>
  ---
  Body: <prose, 300–500 words, entity wikilinks inline>
  ---
  Entities: <comma-separated canonical names actually mentioned>
  Lang: <id|en>

INTERACTION_MODE:
  Direct. No questions. No meta-commentary. Output only.

GATE_AWARENESS:
  epistemic_status={status}
  confidence={score}
  new_entities={list}
  new_cooccurrences={list}
  source_count={n}
  If status is EMERGING: use hedged language throughout.
  If new entities or co-occurrences exist: mention them explicitly — they are the story.
```

### LLM invocation
Use Claude API (Haiku 4.5 for cost, Sonnet 4.6 for quality — configurable).
Fallback: opencode run --model opencode/minimax-m3-free if API key not set.

```python
# writer.py — LLM call
import anthropic

client = anthropic.Anthropic()
response = client.messages.create(
    model="claude-haiku-4-5-20251001",  # fast + cheap, sufficient for structured analysis
    max_tokens=1024,
    messages=[{"role": "user", "content": writer_context}]
)
```

One call per signal. Skips signals already written this run (check hermes_articles table).
Cost per article: ~$0.0003 (Haiku) × N signals per run. Negligible.

## New DB Table

```sql
CREATE TABLE hermes_articles (
    id               TEXT PRIMARY KEY,   -- hrm-{signal_id}
    signal_id        TEXT NOT NULL REFERENCES signals(id),
    cluster_id       TEXT NOT NULL,
    title            TEXT NOT NULL,
    body             TEXT NOT NULL,
    entities_json    TEXT DEFAULT '[]',  -- canonical entity names used
    epistemic_status TEXT NOT NULL,
    confidence       REAL NOT NULL,
    lang             TEXT DEFAULT 'id',
    written_at       TEXT NOT NULL,
    UNIQUE(signal_id)                    -- one article per signal
);
```

## Hermes Article File Format

File: `hermes/YYYY-MM-DD/{signal-id}.md`

```markdown
---
hermes_id: hrm-sig-001
signal_id: sig-001
cluster_id: clust-xyz
epistemic_status: emerging
confidence: 0.71
entities: [Prabowo Subianto, KPK, Dana Haji]
sources: [CNN Indonesia, Antara]
source_count: 2
lang: id
written_at: 2026-06-27T07:30:00+07:00
---

# KPK Sasar Dana Haji: Entitas Baru, Pola Lama

[[KPK]] kembali bergerak ke wilayah yang selama ini sensitif secara politik.
Dua sumber melaporkan bahwa komisi antirasuah itu kini menyelidiki pengelolaan
[[Dana Haji]] — sebuah entitas yang *baru pertama kali muncul* dalam radar Datagateway
hari ini — dalam lingkup Kementerian Agama.

Yang menjadikan perkembangan ini signifikan bukan semata kasusnya, melainkan
polanya: [[KPK]] dan [[Prabowo Subianto]] telah bersama-sama muncul dalam
23 artikel sejak Mei, dengan konteks yang berkisar dari reformasi kabinet hingga
anggaran pertahanan. Kemunculan [[Dana Haji]] sebagai entitas baru dalam
jaringan ini menandai perluasan investigasi ke sektor yang lebih luas.

Fakta yang dikonfirmasi kedua sumber: pemeriksaan dijadwalkan 2 Juli 2026.
Yang masih diperdebatkan: nilai dana yang dipersoalkan — CNN Indonesia menyebut
angka Rp 2,3 triliun, sementara Antara belum mengonfirmasi nominal.

*Yang perlu dipantau: apakah entitas ketiga dari jaringan [[KPK]]-[[Prabowo Subianto]]
akan muncul dalam pemanggilan berikutnya.*

---
*Ditulis oleh Hermes · EMERGING (71%) · 2 sumber · [[KPK]] · [[Prabowo Subianto]] · [[Dana Haji]]*
*Sumber: [[cnn_indonesia_kpk-abc123]], [[antara_kpk-def456]]*
```

## What Is Deliberately Excluded

- No human editorial review gate in v1 (Hermes writes → publishes directly)
- No article versioning (signal update → new hermes article overwrites old)
- No multi-language output (one article per signal in dominant language)
- No image selection for Hermes articles (text only in v1; hero image from signal's
  most-authoritative source article can be added in v2)

## Verification

- [ ] `hermes/` directory created, `hermes_articles` table populated after run
- [ ] Each Hermes article contains `[[wikilinks]]` for entities
- [ ] EMERGING articles use hedged language ("diduga", "dilaporkan")
- [ ] New entity flagged with `*baru pertama kali muncul*` or equivalent in body
- [ ] Article word count between 250–550 words
- [ ] Running pipeline twice does not produce duplicate hermes articles (UNIQUE signal_id)
- [ ] Haiku cost per run: < $0.01 for ≤ 20 signals
