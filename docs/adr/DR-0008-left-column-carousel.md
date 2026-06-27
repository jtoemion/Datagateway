# DR-0008: Left Column Hermes Carousel UI

Date: 2026-06-27
Status: Accepted
Session: persona-brainstorm-20260627-001 (addendum)
Node location: `render/hermes.py`, `render/gateway.py` (layout restructure)
Depends on: DR-0007 (Hermes writer produces the articles)

## Context

Hermes articles exist in the DB and in `hermes/` .md files but have no UI surface.
The current dashboard is full-width with tabs. The Hermes column is a new persistent
panel — always visible regardless of active tab — showing synthesized analysis as
vertically-scrolling cards that drift upward slowly and pause on hover.

## Decision

Add a fixed-width left column (280px) to the dashboard layout. The left column renders
Hermes articles as cards in a step-and-hold auto-scroll carousel. Main content (tabs)
fills the remaining width. On mobile, the column becomes a horizontal strip at page top.

## Layout Structure

```
┌─────────────────────────────────────────────────────────────────┐
│  HEADER (full width)                                            │
├─────────────────┬───────────────────────────────────────────────┤
│  HERMES  280px  │  [ World News ]  [ Football ]  [ More ]       │
│  ─────────────  │  ─────────────────────────────────────────    │
│  [ card  ]  ▲  │                                               │
│  [ card  ]  │  │  news grid / football content                 │
│  [ card  ]  │  │                                               │
│  [ card  ]  ▼  │                                               │
│  (scrolling)    │                                               │
│  ─────────────  │                                               │
│  "HERMES"       │                                               │
│  N analyses     │                                               │
└─────────────────┴───────────────────────────────────────────────┘
```

Mobile (< 768px): left column collapses to a horizontal strip above the tabs.
Cards in mobile strip: horizontal scroll, no auto-scroll.

## What to Build

### `render/hermes.py` (CODE)
Input: list[HermesArticle] from `hermes_articles` table (ordered by written_at DESC)
Output: left column HTML string

#### Card design (per article)

```
┌─────────────────────────────┐
│ HERMES  [EMERGING 71%]      │  ← badge row
│                             │
│ KPK Sasar Dana Haji:        │  ← title (2 lines max, truncate)
│ Entitas Baru, Pola Lama     │
│                             │
│ KPK kembali bergerak ke     │  ← excerpt (3 lines, ~120 chars)
│ wilayah yang selama ini...  │
│                             │
│ 2 sumber · 2h ago   Read → │  ← footer
└─────────────────────────────┘
```

Epistemic pill colors:
```
CONFIRMED  → #4ade80 (green)
REPORTED   → #60a5fa (blue)
EMERGING   → #fbbf24 (amber)
CONTESTED  → #f87171 (rose/red)
```

HERMES badge: purple gradient (`#7c3aed` → `#a855f7`).
Card background: `#1a1f2e` (slightly lighter than page bg).
Border-left: 3px solid epistemic pill color (color-coding at a glance).

#### Confidence display (EMERGING only)
Thin progress bar below the pill: `width: {confidence * 100}%`, amber fill.
Hidden for CONFIRMED/REPORTED/CONTESTED (confidence is not a useful signal there).

#### Scroll behavior (JS)
```javascript
// Step-and-hold carousel
const DWELL_MS = 6000;    // each card stays in view 6 seconds
const SCROLL_MS = 400;    // transition to next card (smooth)
const RESUME_DELAY = 2000; // ms after mouse-leave before resuming

let timer, paused = false;

function nextCard() {
  if (paused) return;
  // move first card to end of list (circular)
  const col = document.getElementById('hermes-col');
  const first = col.querySelector('.h-card');
  if (!first) return;
  col.style.transition = `transform ${SCROLL_MS}ms ease`;
  col.style.transform = `translateY(-${first.offsetHeight + 12}px)`;  // 12 = gap
  setTimeout(() => {
    col.style.transition = 'none';
    col.style.transform = 'translateY(0)';
    col.appendChild(first);   // move to bottom
  }, SCROLL_MS);
}

document.getElementById('hermes-panel').addEventListener('mouseenter', () => {
  paused = true; clearInterval(timer);
});
document.getElementById('hermes-panel').addEventListener('mouseleave', () => {
  setTimeout(() => { paused = false; timer = setInterval(nextCard, DWELL_MS); }, RESUME_DELAY);
});

timer = setInterval(nextCard, DWELL_MS);
```

Cards are circular: after the last card scrolls past, the first appears again.
If only 1 article: no scroll (single card stays static).
If 0 articles: empty state shown (no scroll).

#### Empty state
```html
<div class="h-empty">
  <div class="h-empty-icon">🔍</div>
  <p>Hermes sedang membaca berita.</p>
  <span>Analisis tersedia setelah run berikutnya.</span>
</div>
```

#### "Read →" link
Opens `article.html?id=hrm-{signal_id}` — the article viewer shows the Hermes
article body, with the vis.js graph showing the cluster source articles as connected nodes
(cluster edges = new edge type, color: purple).

### `render/gateway.py` changes (GATEWAY)
- Load `hermes_articles` from DB (latest 20)
- Pass to `render/hermes.py` → left column HTML
- Restructure `build_html()` to wrap existing tab content in a two-panel flex layout
- Left panel: hermes column (280px fixed, full viewport height, overflow hidden)
- Right panel: existing tabs (flex-grow: 1)

### Layout CSS additions

```css
.layout {
  display: flex;
  align-items: flex-start;
  gap: 0;
  min-height: calc(100vh - 80px);  /* below header */
}

.hermes-panel {
  width: 280px;
  min-width: 280px;
  height: calc(100vh - 80px);
  position: sticky;
  top: 80px;
  overflow: hidden;
  border-right: 1px solid var(--border);
  background: var(--surface);
  display: flex;
  flex-direction: column;
}

.hermes-header {
  padding: 14px 16px 10px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.hermes-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 1.5px;
  background: linear-gradient(135deg, #7c3aed, #a855f7);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}
.hermes-count { font-size: 11px; color: var(--text-muted); }

.hermes-col { flex: 1; overflow: hidden; padding: 8px; }

.h-card {
  background: #1a1f2e;
  border-radius: 8px;
  border-left: 3px solid var(--epistemic-color);
  padding: 12px;
  margin-bottom: 12px;
  cursor: pointer;
  transition: background .15s;
}
.h-card:hover { background: #1e2438; }

.h-badge-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.h-badge {
  font-size: 9px; font-weight: 700; letter-spacing: 1px;
  padding: 2px 6px; border-radius: 4px;
  background: linear-gradient(135deg, #7c3aed, #a855f7); color: white;
}
.h-pill {
  font-size: 9px; font-weight: 700; letter-spacing: 0.5px;
  padding: 2px 6px; border-radius: 4px; color: white;
}
.pill-confirmed  { background: #166534; color: #4ade80; }
.pill-reported   { background: #1e3a5f; color: #60a5fa; }
.pill-emerging   { background: #78350f; color: #fbbf24; }
.pill-contested  { background: #7f1d1d; color: #f87171; }

.h-confidence {
  height: 2px; background: #253040; border-radius: 2px; margin-bottom: 8px;
}
.h-confidence-fill { height: 100%; background: #fbbf24; border-radius: 2px; }

.h-title {
  font-size: 13px; font-weight: 600; line-height: 1.4;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden; margin-bottom: 6px; color: var(--text);
}
.h-excerpt {
  font-size: 11px; color: var(--text-muted); line-height: 1.5;
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical;
  overflow: hidden; margin-bottom: 10px;
}
.h-footer {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 10px; color: var(--text-muted);
}
.h-read { color: #a855f7; font-weight: 600; text-decoration: none; }
.h-read:hover { color: #c084fc; }

@media (max-width: 768px) {
  .layout { flex-direction: column; }
  .hermes-panel {
    width: 100%; height: auto; position: static;
    border-right: none; border-bottom: 1px solid var(--border);
  }
  .hermes-col { display: flex; overflow-x: auto; padding: 8px; gap: 10px; }
  .h-card { min-width: 220px; margin-bottom: 0; }
}
```

## What Is Deliberately Excluded

- No Hermes article in the main news grid (Hermes column is separate and always left)
- No filtering/search within the Hermes column in v1
- No "more" link / pagination — shows latest 20 articles, carousel loops
- No read/unread tracking
- No mobile auto-scroll (horizontal strip, manual swipe only on mobile)
- No share button in v1

## Verification

- [ ] Left column appears on desktop with 280px width, sticky below header
- [ ] Cards show HERMES badge + epistemic pill with correct color per status
- [ ] EMERGING cards show confidence progress bar; CONFIRMED/REPORTED do not
- [ ] Auto-scroll advances every 6 seconds, pauses on mouse-enter, resumes after 2s mouse-leave
- [ ] With 1 article: no scroll, card stays static
- [ ] With 0 articles: empty state shown
- [ ] "Read →" link opens article.html correctly
- [ ] Mobile (< 768px): horizontal strip, no auto-scroll
- [ ] Main content area (tabs) unaffected by layout change
