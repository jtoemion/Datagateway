# Datagateway — UI Design Review & Redesign Plan

**Date:** 2026-06-27
**Status:** Plan only — no implementation
**Scope:** Critical review of current dashboard + proposed redesign for the intelligence-era product

---

## TL;DR — The Core Problem

Datagateway started as a **news reader** and is becoming an **OSINT intelligence
workstation**. The DRs added entities (DR-0005), signals (DR-0006), and graph-aware
Hermes analysis (DR-0007). But the UI is still a 150-card news grid with intelligence
features bolted on as a narrow sidebar (DR-0008).

**The product's value is now synthesis, but the UI still leads with raw feed.**

The redesign is one inversion: **signal-first, feed-on-demand**. What Hermes concluded
goes to the center and top. The 150 raw articles become the substrate you drill into,
not the front page.

---

## Part 1 — Critical Review of Current UI

### What works (keep)
- Dark theme is appropriate for a dense information tool; the CSS variable system is clean
- 16:9 image cards are scannable; the source-glyph + color-coding is a good identity signal
- Football tab's hero + carousel + odds table is genuinely well-composed
- Wikilink copy affordance is a nice Obsidian-native touch
- Card hover lift + the `onerror` image-removal fallback show real polish

### What's wrong (fix)

**1. Flat hierarchy — everything is the same visual weight.**
150 cards, identical size, identical treatment. A FIFA squad-list filler article looks
exactly as important as a breaking KPK investigation. The UI does zero prioritization.
The whole point of the signal layer is that *some news matters more* — the UI must show it.

**2. Feed-first contradicts the product thesis.**
The first thing the user sees is the raw firehose. But the sharpest artifact Datagateway
now produces — the Hermes analysis — is relegated to a 280px auto-scrolling sidebar.
The most valuable content gets the least space and a reading-hostile interaction.

**3. The knowledge graph is buried.**
The entity graph (vis.js) lives inside `article.html?id=...` — you only reach it after
clicking into a single article. But the graph IS the intelligence product. It should be a
first-class destination, not a detail-page widget.

**4. Stats are vanity, not actionable.**
"Today: 47 · Total: 391 · Sources: 10 · Latest: 2026-06-27." None of these change a
decision. Prime real estate spent on counters. Intelligence stats would be: *N active
clusters, M emerging signals, K new entities today, top mover.*

**5. No epistemic visual language outside Hermes.**
DR-0008 introduces confirmed/reported/emerging/contested pills — but only on Hermes cards.
Confidence needs to be a consistent visual system across the *entire* app: a feed article
that's part of a CONFIRMED cluster should show it. Right now epistemic state is siloed.

**6. Search is underweighted.**
DR-0001 makes BM25 search the primary navigation tool, but it's a thin input wedged in a
toolbar. If search is how you navigate, it deserves command-bar prominence (⌘K).

**7. Generic identity.**
The "dark GitHub dashboard" look is competent but anonymous. An OSINT product can carry a
sharper, more distinct visual identity — closer to a Bloomberg terminal or a SOC console
than a blog.

---

## Part 2 — Design Principles for the Redesign

1. **Signal over feed.** Synthesis is the homepage. Raw articles are one drill-down away.
2. **Weight = significance.** Visual size, position, and color encode how much something matters.
3. **Epistemic honesty is a visual system.** Confidence/status has one consistent language everywhere.
4. **The graph is a place, not a widget.** Entities and their connections are a primary view.
5. **One keystroke to anything.** Command-bar search (⌘K) is the spine of navigation.
6. **Calm by default, alive on demand.** No motion that fights reading; motion only to draw the eye to what changed.

---

## Part 3 — Information Architecture (the inversion)

Replace the current `[World News] [Football] [More]` tab model with **four modes**, ranked
by altitude (synthesis → raw):

```
┌──────────────────────────────────────────────────────────────────────┐
│  ◆ DATAGATEWAY        ⌘K Search anything…        ✅ Run 07:03  ◑ theme │  ← command bar
├──────────────────────────────────────────────────────────────────────┤
│  [ BRIEFING ]  [ FEED ]  [ GRAPH ]  [ ENTITIES ]                       │  ← mode switch
└──────────────────────────────────────────────────────────────────────┘
```

| Mode | What it is | Powered by |
|---|---|---|
| **Briefing** (default) | Hermes analyses ranked by significance. "What's actually happening today." | DR-0007 |
| **Feed** | The current card grid — raw articles, filters, search. The substrate. | existing + DR-0001 |
| **Graph** | Full-screen entity knowledge graph. Explorable, filterable, time-scrubbable. | DR-0005 |
| **Entities** | Directory + profile pages. Click an entity anywhere → lands here. | DR-0005 |

Football becomes a **filter/section within Feed** (it's a category), not a top-level peer
of the intelligence modes. The hero+odds treatment is preserved as a Feed sub-view.

---

## Part 4 — Mode-by-Mode Layout

### 4.1 BRIEFING (the new homepage)

This is the biggest change. Hermes analyses become the hero content, ranked by a
**significance score** (new entities + new co-occurrences + source count + recency).

```
┌─────────────────────────────────────────────────────────────────────┐
│  TODAY'S BRIEFING                          3 emerging · 2 confirmed   │
│  ───────────────────────────────────────────────────────────────────│
│                                                                       │
│  ┌─────────────────────────────────────────┐  ┌──────────────────┐  │
│  │ ⚡ EMERGING · 71%          KPK · Dana Haji│  │ CONFIRMED · 4 src│  │
│  │                                           │  │                  │  │
│  │ KPK Sasar Dana Haji:                      │  │ US Strikes Iran  │  │
│  │ Entitas Baru, Pola Lama                   │  │ After Hormuz...  │  │
│  │                                           │  │                  │  │
│  │ KPK kembali bergerak ke wilayah yang      │  │ Centcom confirms │  │
│  │ selama ini sensitif... [[Dana Haji]]      │  │ strikes on...    │  │
│  │ muncul pertama kali hari ini.             │  │                  │  │
│  │                                           │  │ [[Iran]] [[US]]  │  │
│  │ ▸ 2 sumber  ▸ 3 entitas  ▸ graph          │  │ ▸ 4 src ▸ graph  │  │
│  └─────────────────────────────────────────┘  └──────────────────┘  │
│   ↑ lead story (significance-ranked, large)     ↑ secondary (smaller)│
│                                                                       │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                  │
│  │ REPORTED     │ │ EMERGING 44% │ │ CONTESTED    │   ← tertiary row  │
│  │ Cabinet...   │ │ Trade pact...│ │ Toll figures │                  │
│  └──────────────┘ └──────────────┘ └──────────────┘                  │
└─────────────────────────────────────────────────────────────────────┘
```

- **Significance-weighted sizing**: lead story large, secondary medium, rest in a grid.
  This directly fixes the flat-hierarchy problem.
- Each Hermes card carries the epistemic pill + confidence + entity chips + a "graph"
  affordance that opens GRAPH mode focused on that cluster.
- **This replaces DR-0008's auto-scroll sidebar concept** — see §6 for the recommendation.

### 4.2 FEED (the current grid, refined)

Keep the card grid, but:
- Cards inherit **cluster status border-tint** when they belong to a scored cluster
  (a CONFIRMED-cluster article gets a faint green left edge). Epistemic language everywhere.
- A "**N articles in this cluster**" chip on cards that are part of a multi-source story,
  linking to the Hermes analysis. Connects raw → synthesis.
- Football hero/odds becomes a collapsible section when the `football` category filter is on.
- Search promoted to the command bar (⌘K); the inline toolbar search remains as a
  scoped "filter within feed."

### 4.3 GRAPH (new first-class view)

Promote the vis.js graph out of the article detail page to a full-screen mode.

```
┌─────────────────────────────────────────────────────────────────────┐
│  KNOWLEDGE GRAPH        ◉ entities ◉ articles ◉ clusters   ⏱ [====▸] │
│  ───────────────────────────────────────────────────────────────────│
│                          ●KPK ───── ●Prabowo                          │
│                         ╱   │    ╲      │                             │
│                   ●DanaHaji │  ●DPR  ●Kabinet                         │
│                     ⚡new    │                                          │
│                                                                       │
│  [ Filter: PERSON ◉ ORG ◉ PLACE ◯ CONCEPT ◯ ]    [ Layout: force ▾ ] │
└─────────────────────────────────────────────────────────────────────┘
```

- Node size = `article_count` (entity prominence). New entities pulse with the ⚡ marker.
- Edge weight = co-occurrence count.
- **Time scrubber** (⏱) replays the graph forming over the last N days — watch the network grow.
- Click a node → ENTITIES profile in the context panel.
- Filter by entity type, by cluster, by date window.

### 4.4 ENTITIES (directory + profile)

The entity pages from DR-0005 get a real UI.

```
┌──────────────────────────┬──────────────────────────────────────────┐
│  ENTITIES                 │  Prabowo Subianto            PERSON · 47x │
│  ──────────────           │  ─────────────────────────────────────── │
│  🔍 filter…               │  Active since 2026-05-01                  │
│                           │                                           │
│  ● Prabowo Subianto  47   │  Connected:                               │
│  ● KPK               31   │   [[KPK]] 23x  [[Jokowi]] 18x  [[DPR]] 11x│
│  ● Joko Widodo       28   │                                           │
│  ⚡ Dana Haji          1   │  Timeline:                                │
│  ● DPR               19   │   ▂▃▅▇▆▅▃▂  (mentions over 30 days)        │
│  …                        │                                           │
│                           │  Recent articles:                         │
│  [PERSON][ORG][PLACE]     │   2026-06-27 · KTT ASEAN                   │
│                           │   2026-06-25 · Defense pact               │
└──────────────────────────┴──────────────────────────────────────────┘
```

- Left: searchable, sortable entity list (by mentions, recency, type).
- Right: profile — connected entities, mention timeline sparkline, recent articles,
  and any Hermes analyses the entity appears in.

---

## Part 5 — The Epistemic Visual Language (system-wide)

One consistent encoding for "how sure are we," used on Hermes cards, feed cards,
graph nodes, and signal pages alike.

One consistent encoding for "how sure are we" — the five states defined by DR-0012's
provenance-aware scorer — used on Hermes cards, feed cards, graph nodes, and signal pages.

| Status | Color | Use | Meaning (DR-0012) |
|---|---|---|---|
| **CONFIRMED** | `#4ade80` green | solid pill, solid border | ≥3 **independent** origins, consistent facts |
| **REPORTED** | `#60a5fa` blue | solid pill | ≥2 independent origins, OR 1 primary outlet |
| **SINGLE_SOURCE_AMPLIFIED** | `#fb923c` orange | pill + `↻ 1 origin` | widely run, but traces to ONE origin (echo) |
| **EMERGING** | `#fbbf24` amber + % | pill **with confidence bar** | single, non-primary; show probability |
| **CONTESTED** | `#f87171` rose | pill + ⚠ | independent sources contradict on a numeric fact |

**Rule:** confidence percentage shown **only** for EMERGING. The other four are epistemic
*states*, not probabilities — a number there is noise.

**`SINGLE_SOURCE_AMPLIFIED` is the most important visual to get right** — it's the echo-chamber
case that previously masqueraded as CONFIRMED. The `↻ 1 origin` marker must read as a
*caution*, not corroboration. Distinct orange (not the amber of EMERGING) so the user never
confuses "uncorroborated but original" with "everyone copied one wire."

**Significance markers** (orthogonal to confidence):
- `⚡` new entity / first appearance today — gated by DR-0012 §6 (not extraction noise)
- `⚠` new co-occurrence — gated by DR-0012 §3 nPMI (meaningful, not coincidental prominence)
These are the analytical leverage points; they earn a distinct glyph that draws the eye.

### Review-queue affordance (DR-0012 §7)
Low-confidence synthesis (`SINGLE_SOURCE_AMPLIFIED`, `CONTESTED`, low `EMERGING`) does NOT
auto-publish to the Briefing/rail. A small **Review** badge in the command bar shows the
`pending_review` count; clicking opens a one-tap approve/discard queue. The human stays in
the loop exactly where the machine is least sure.

---

## Part 6 — The Hermes Rail: Recommendation on Auto-Scroll

You asked for a left column with cards that auto-scroll slowly (DR-0008). Here's my honest
assessment and a recommendation — **your call**, this is a preference, not a correctness issue.

**The tension:** auto-scrolling motion and *reading* are in direct conflict. A card that
drifts or swaps out from under the user while they're mid-sentence is frustrating. Slow
motion is also easy to not notice at all, so it doesn't earn its cost.

**Three options:**

| Option | What | Tradeoff |
|---|---|---|
| **A — Briefing-first (recommended)** | Hermes analyses become the BRIEFING homepage (§4.1), significance-ranked, static, full-width. No rail. | Best readability + hierarchy. Drops the auto-scroll motion you described. |
| **B — Rail kept, refined** | Keep the 280px rail, but step-and-hold (6s dwell, pause-on-hover) as already specced in DR-0008. | Keeps your motion concept. Rail is cramped for analytical prose. |
| **C — Hybrid** | BRIEFING is the homepage (A), AND a thin "latest Hermes" ticker rail persists on FEED/GRAPH modes for ambient awareness. | Best of both, more to build. |

My recommendation is **C**: lead with Briefing (synthesis deserves center stage), but keep
a slim Hermes ticker on the other modes so the analysis is always one glance away. The
ticker can carry the gentle auto-advance you wanted — there, ambient motion *helps* because
you're not trying to read it, just stay aware of it.

---

## Part 7 — Typography, Color, Identity

- **Type:** Introduce a display/mono pairing. Headlines in a tight grotesk (Space Grotesk /
  Inter Tight); body stays system-ui; **monospace for data** (odds, IDs, confidence %, counts,
  timestamps) — reinforces the "instrument" feel. Current all-system-ui reads as a blog.
- **Color:** Keep the dark base (`#0b0f15`). Add the epistemic palette as semantic tokens
  (`--confirmed`, `--reported`, `--emerging`, `--contested`) so it's consistent everywhere.
  Reserve the Hermes purple (`#a855f7`) strictly for AI-authored content — it should always
  signal "a machine wrote this," never decoration.
- **Density:** Offer a **compact/comfortable toggle**. Analysts want density; casual reading
  wants air. One CSS class on `<body>`.
- **Identity:** Lean into "intelligence console" — hairline borders, mono accents, a subtle
  scanline/grid texture on empty states, status-light dots (●) for run health and source liveness.

---

## Part 8 — Responsive

- **Desktop (>1100px):** full four-mode layout, two-panel where noted, graph full-bleed.
- **Tablet (768–1100px):** context panels become slide-over drawers; briefing drops to single column.
- **Mobile (<768px):** mode switch becomes a bottom tab bar; Briefing is a vertical stack;
  Graph is view-only (pinch-zoom, no time scrubber); entity profiles are full-screen pushes.
  No auto-scroll on mobile (matches DR-0008 exclusion).

---

## Part 9 — Phasing (maps to existing DRs)

| Phase | Deliverable | Depends on | New DR? |
|---|---|---|---|
| **P1** | Epistemic visual system (tokens + pills) + command-bar search | DR-0001 | extend DR-0001 |
| **P2** | FEED refinements: cluster-status tints, "in cluster" chips | DR-0006 | extend DR-0008 |
| **P3** | BRIEFING mode (significance-ranked Hermes homepage) | DR-0007 | **DR-0009** |
| **P4** | GRAPH mode (promote vis.js to full-screen + time scrubber) | DR-0005 | **DR-0010** |
| **P5** | ENTITIES directory + profile pages | DR-0005 | **DR-0011** |
| **P6** | Hermes ticker rail (option C) + compact/comfortable toggle | DR-0007 | revise DR-0008 |

DR-0008 (left-column auto-scroll) should be **revised**, not implemented as-is — superseded
by BRIEFING (DR-0009) as the primary surface, with the rail demoted to an optional ambient
ticker (Part 6, option C).

---

## Part 10 — Open Questions (for Judah)

1. **Auto-scroll:** Option A, B, or C from Part 6? (I recommend C.)
2. **Default mode:** Should the dashboard open on BRIEFING (synthesis) or FEED (raw)?
   My instinct: Briefing — but if you mostly browse raw news, Feed.
3. **Football:** Demote to a Feed category (my proposal), or keep as a top-level mode?
   It's the one non-OSINT vertical and may deserve to stay separate.
4. **Identity ambition:** Refine the existing dark dashboard, or commit to a stronger
   "intelligence console" redesign (Part 7)? The latter is more work, more distinct.
5. **Density default:** compact (analyst) or comfortable (reader)?
6. **Graph time-scrubber:** worth the build, or is a static current-state graph enough for v1?
```
