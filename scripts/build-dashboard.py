#!/usr/bin/env python3
"""
Datagateway — Dashboard Builder v2
Professional card layout with wikilinks, metadata, and source-colored badges.
"""

import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

WIB = timezone(timedelta(hours=7))
REPO_ROOT = Path(__file__).resolve().parent.parent
NEWS_DIR = REPO_ROOT / "news"
DASHBOARD_DIR = REPO_ROOT / "dashboard"

SOURCE_COLORS = {
    "CNN Indonesia": ("#e31e24", "#e31e2433"),
    "Detik": ("#ffffff", "#ffffff22"),
    "CNBC Indonesia": ("#0055a5", "#0055a533"),
    "Antara": ("#1b5e20", "#1b5e2033"),
    "Republika": ("#f7941e", "#f7941e33"),
    "BBC Indonesia": ("#bb1919", "#bb191933"),
    "BBC News": ("#bb1919", "#bb191933"),
    "NY Times": ("#000000", "#33333333"),
}
DEFAULT_SOURCE_COLOR = ("#58a6ff", "#58a6ff33")

SOURCE_GLYPH = {
    "CNN Indonesia": "C",
    "Detik": "D",
    "CNBC Indonesia": "B",
    "Antara": "A",
    "Republika": "R",
    "BBC Indonesia": "B",
    "BBC News": "B",
    "NY Times": "N",
}


def parse_md_article(filepath: Path) -> dict | None:
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception:
        return None

    frontmatter = {}
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1].strip()
            body = parts[2].strip()
            for line in fm_text.split("\n"):
                line = line.strip()
                if ":" in line:
                    key, _, val = line.partition(":")
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    frontmatter[key] = val

    excerpt = ""
    lines = body.split("\n")
    in_body = False
    for line in lines:
        if line.startswith("# "):
            continue
        if line.startswith("**Sumber:**"):
            in_body = True
            continue
        if in_body and line.strip() and not line.startswith("---"):
            excerpt = line.strip()
            excerpt = re.sub(r'\*\*(.*?)\*\*', r'\1', excerpt)
            excerpt = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', excerpt)
            break
    if not excerpt:
        excerpt = body[:250].replace("\n", " ").strip()

    return {
        "id": frontmatter.get("id", ""),
        "source": frontmatter.get("source", ""),
        "title": frontmatter.get("title", ""),
        "url": frontmatter.get("url", ""),
        "date": frontmatter.get("date", ""),
        "date_wib": frontmatter.get("date_wib", ""),
        "category": frontmatter.get("category", ""),
        "lang": frontmatter.get("lang", ""),
        "excerpt": excerpt[:350],
        "filename": filepath.name,
        "relpath": str(filepath.relative_to(REPO_ROOT)),
        "wikilink": f"[[{filepath.relative_to(REPO_ROOT)}]]",
    }


def collect_articles() -> list[dict]:
    articles = []
    if not NEWS_DIR.exists():
        return articles
    for date_dir in sorted(NEWS_DIR.iterdir(), reverse=True):
        if not date_dir.is_dir():
            continue
        for f in sorted(date_dir.iterdir(), reverse=True):
            if f.suffix == ".md":
                art = parse_md_article(f)
                if art and art["title"]:
                    articles.append(art)
    return articles


def esc(text: str) -> str:
    """HTML-escape all the things."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def build_html(articles: list[dict]) -> str:
    sources = sorted(set(a["source"] for a in articles if a["source"]))
    categories = sorted(set(a["category"] for a in articles if a["category"]))
    langs = sorted(set(a["lang"] for a in articles if a["lang"]))

    now = datetime.now(WIB)
    today = now.strftime("%Y-%m-%d")
    today_count = sum(1 for a in articles if a["date"].startswith(today))
    source_count = len(sources)
    total_count = len(articles)
    last_update = now.strftime("%Y-%m-%d %H:%M WIB")
    latest_date = articles[0]["date"][:10] if articles else "—"

    # ── STATS ──
    stats_html = f"""
    <div class="stat-card"><div class="num">{today_count}</div><div class="stat-label">Today</div></div>
    <div class="stat-card"><div class="num">{total_count}</div><div class="stat-label">Total Articles</div></div>
    <div class="stat-card"><div class="num">{source_count}</div><div class="stat-label">Sources</div></div>
    <div class="stat-card"><div class="num">{latest_date}</div><div class="stat-label">Latest</div></div>
"""

    # ── FILTER BUTTONS ──
    def btn(text, count, filter_val, group="source"):
        return f"""<button class="flt" data-g="{group}" data-v="{filter_val}" onclick="toggleFilter(this,'{group}')">{esc(text)} <span class="flt-c">{count}</span></button>"""

    source_btns = "\n      ".join(
        btn(s, sum(1 for a in articles if a["source"] == s), s)
        for s in sources
    )
    cat_btns = "\n      ".join(
        btn(c.title(), sum(1 for a in articles if a["category"] == c), c, "cat")
        for c in categories
    )
    lang_btns = "\n      ".join(
        btn(l.upper(), sum(1 for a in articles if a["lang"] == l), l, "lang")
        for l in langs
    )

    # ── CARDS ──
    cards_html = ""
    for a in articles:
        src = a["source"]
        fg, bg = SOURCE_COLORS.get(src, DEFAULT_SOURCE_COLOR)
        glyph = SOURCE_GLYPH.get(src, src[0].upper())
        date_short = a["date_wib"] or a["date"][:10]
        cat = a["category"].title() if a["category"] else "—"
        title_esc = esc(a["title"])
        excerpt_esc = esc(a["excerpt"])
        wikilink_esc = esc(a["wikilink"])
        relpath_esc = esc(a["relpath"])

        cards_html += f"""
    <article class="card" data-source="{esc(src)}" data-cat="{a['category']}" data-lang="{a['lang']}">
      <div class="card-accent" style="background:{fg}"></div>
      <div class="card-body">
        <div class="card-top">
          <span class="card-glyph" style="background:{bg};color:{fg};border-color:{fg}">{glyph}</span>
          <span class="card-source" style="color:{fg}">{esc(src)}</span>
          <span class="card-lang badge-{a['lang']}">{a['lang']}</span>
          <span class="card-date">{date_short}</span>
        </div>
        <a href="{esc(a['url'])}" target="_blank" rel="noopener" class="card-title">{title_esc}</a>
        <p class="card-excerpt">{excerpt_esc}</p>
        <div class="card-meta">
          <span class="meta-cat">{cat}</span>
          <span class="meta-id">{a['id']}</span>
        </div>
        <div class="card-wiki" onclick="copyWiki(this)" title="Click to copy wikilink">
          <span class="wiki-label">wikilink</span>
          <code class="wiki-link">{wikilink_esc}</code>
          <span class="wiki-copy">copy</span>
        </div>
        <div class="card-actions">
          <a href="{esc(a['url'])}" target="_blank" rel="noopener" class="act act-ext">Open Original →</a>
          <a href="file://{esc(str(REPO_ROOT / a['relpath']))}" class="act act-md">📄 .md</a>
        </div>
      </div>
    </article>"""

    # ── VIEWBOX overlay ──
    viewbox_html = """
  <div id="viewbox" class="viewbox" onclick="closeViewbox(event)">
    <div class="viewbox-content">
      <button class="viewbox-close" onclick="closeViewbox()">✕</button>
      <div id="viewbox-body"></div>
    </div>
  </div>"""

    html = f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Datagateway — OSINT Dashboard</title>
<style>
  *,*::before,*::after {{ box-sizing:border-box; margin:0; padding:0; }}
  :root {{
    --bg:#0b0f15; --surface:#131a24; --surface-2:#1c2533;
    --border:#253040; --text:#e2e8f0; --text-muted:#8395a8;
    --accent:#60a5fa; --green:#4ade80; --amber:#fbbf24; --rose:#f87171;
    --radius:10px; --font:system-ui,-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
  }}
  html {{ font-size:15px; }}
  body {{ font-family:var(--font); background:var(--bg); color:var(--text); line-height:1.6; min-height:100vh; }}
  .container {{ max-width:1360px; margin:0 auto; padding:0 20px; }}

  /* ─── HEADER ─── */
  header {{ padding:28px 0 16px; border-bottom:1px solid var(--border); margin-bottom:24px; }}
  .head-row {{ display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:12px; }}
  .head-logo {{ display:flex; align-items:center; gap:14px; }}
  .head-logo .icon {{ width:40px; height:40px; border-radius:10px; background:linear-gradient(135deg,#60a5fa,#4ade80); display:flex; align-items:center; justify-content:center; font-size:20px; font-weight:700; color:#0b0f15; }}
  .head-logo h1 {{ font-size:24px; font-weight:700; letter-spacing:-0.5px; }}
  .head-logo h1 span {{ background:linear-gradient(135deg,var(--accent),var(--green)); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }}
  .head-info {{ text-align:right; font-size:13px; color:var(--text-muted); line-height:1.5; }}

  /* ─── STATS ─── */
  .stats {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin-bottom:24px; }}
  .stat-card {{ background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); padding:16px; text-align:center; }}
  .stat-card .num {{ font-size:30px; font-weight:700; color:var(--accent); line-height:1.2; }}
  .stat-card .stat-label {{ font-size:11px; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.5px; margin-top:2px; }}

  /* ─── TOOLBAR ─── */
  .toolbar {{ display:flex; flex-wrap:wrap; gap:10px; margin-bottom:18px; align-items:center; }}
  .toolbar .srch {{ flex:1; min-width:200px; padding:9px 14px; border-radius:var(--radius); border:1px solid var(--border); background:var(--surface); color:var(--text); font-size:13px; outline:none; transition:border .2s; }}
  .toolbar .srch:focus {{ border-color:var(--accent); }}
  .toolbar .srch::placeholder {{ color:var(--text-muted); }}

  .flt-group {{ display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px; }}
  .flt-group .flt-glabel {{ font-size:10px; text-transform:uppercase; letter-spacing:0.5px; color:var(--text-muted); padding:6px 8px 0 0; min-width:50px; }}
  .flt {{ display:inline-flex; align-items:center; gap:5px; padding:5px 12px; border-radius:20px; border:1px solid var(--border); background:var(--surface); color:var(--text); font-size:12px; cursor:pointer; transition:all .15s; white-space:nowrap; }}
  .flt:hover {{ border-color:var(--accent); background:var(--surface-2); }}
  .flt.on {{ background:var(--accent); color:#0b0f15; border-color:var(--accent); font-weight:600; }}
  .flt.on .flt-c {{ background:rgba(0,0,0,.2); color:#0b0f15; }}
  .flt .flt-c {{ display:inline-flex; align-items:center; justify-content:center; min-width:18px; height:18px; border-radius:9px; background:var(--surface-2); padding:0 5px; font-size:10px; color:var(--text-muted); }}
  .flt-clear {{ border-style:dashed; color:var(--text-muted); }}
  .flt-clear.on {{ border-style:solid; }}

  /* ─── GRID ─── */
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(340px,1fr)); gap:14px; margin-bottom:28px; }}

  /* ─── CARD ─── */
  .card {{ display:flex; flex-direction:column; background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); overflow:hidden; transition:transform .15s,box-shadow .15s; position:relative; }}
  .card:hover {{ transform:translateY(-3px); box-shadow:0 8px 24px rgba(0,0,0,.3); }}
  .card-accent {{ height:3px; flex-shrink:0; }}
  .card-body {{ padding:14px 16px 12px; display:flex; flex-direction:column; flex:1; }}

  .card-top {{ display:flex; align-items:center; gap:8px; margin-bottom:8px; }}
  .card-glyph {{ width:26px; height:26px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:11px; font-weight:700; border:1.5px solid; flex-shrink:0; }}
  .card-source {{ font-size:12px; font-weight:600; letter-spacing:0.2px; }}
  .card-lang {{ font-size:9px; font-weight:700; text-transform:uppercase; padding:1px 6px; border-radius:3px; letter-spacing:0.5px; }}
  .badge-id {{ background:#1f6feb44; color:#60a5fa; }}
  .badge-en {{ background:#4ade8044; color:#4ade80; }}
  .card-date {{ margin-left:auto; font-size:11px; color:var(--text-muted); white-space:nowrap; }}

  .card-title {{ font-size:15px; font-weight:600; line-height:1.4; margin-bottom:6px; color:var(--text); text-decoration:none; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }}
  .card-title:hover {{ color:var(--accent); }}

  .card-excerpt {{ font-size:13px; color:var(--text-muted); line-height:1.55; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; flex:1; margin-bottom:10px; }}

  .card-meta {{ display:flex; gap:10px; font-size:11px; color:var(--text-muted); margin-bottom:8px; }}
  .meta-cat {{ background:#d2992233; color:var(--amber); padding:1px 7px; border-radius:3px; font-weight:500; }}
  .meta-id {{ font-family:monospace; color:var(--text-muted); opacity:.6;}}

  .card-wiki {{ display:flex; align-items:center; gap:6px; background:var(--surface-2); border-radius:5px; padding:5px 8px; cursor:pointer; transition:background .15s; margin-bottom:8px; user-select:none; }}
  .card-wiki:hover {{ background:var(--border); }}
  .card-wiki.copied {{ background:#4ade8022; }}
  .wiki-label {{ font-size:9px; text-transform:uppercase; letter-spacing:0.5px; color:var(--text-muted); font-weight:600; }}
  .wiki-link {{ font-size:11px; font-family:monospace; color:var(--accent); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1; }}
  .wiki-copy {{ font-size:9px; text-transform:uppercase; color:var(--text-muted); font-weight:600; flex-shrink:0; }}

  .card-actions {{ display:flex; gap:6px; margin-top:auto; }}
  .act {{ display:inline-flex; align-items:center; gap:4px; padding:6px 12px; border-radius:5px; font-size:12px; font-weight:500; text-decoration:none; transition:all .15s; }}
  .act-ext {{ background:var(--accent); color:#0b0f15; }}
  .act-ext:hover {{ background:#7bb9ff; }}
  .act-md {{ background:var(--surface-2); color:var(--text); border:1px solid var(--border); }}
  .act-md:hover {{ border-color:var(--accent); color:var(--accent); }}

  /* ─── NO RESULTS ─── */
  .no-r {{ display:none; text-align:center; padding:60px 20px; color:var(--text-muted); grid-column:1/-1; }}
  .no-r.show {{ display:block; }}

  /* ─── VIEWBOX ─── */
  .viewbox {{ display:none; position:fixed; inset:0; background:rgba(0,0,0,.7); backdrop-filter:blur(4px); z-index:1000; align-items:center; justify-content:center; }}
  .viewbox.show {{ display:flex; }}
  .viewbox-content {{ background:var(--surface); border:1px solid var(--border); border-radius:12px; max-width:680px; width:90%; max-height:80vh; overflow-y:auto; padding:24px; position:relative; }}
  .viewbox-close {{ position:absolute; top:12px; right:12px; width:32px; height:32px; border-radius:50%; border:none; background:var(--surface-2); color:var(--text); font-size:16px; cursor:pointer; display:flex; align-items:center; justify-content:center; }}
  .viewbox-close:hover {{ background:var(--border); }}
  .viewbox-body {{ white-space:pre-wrap; font-family:monospace; font-size:13px; line-height:1.6; color:var(--text); }}

  /* ─── FOOTER ─── */
  footer {{ border-top:1px solid var(--border); padding:20px 0; margin-top:12px; text-align:center; font-size:12px; color:var(--text-muted); }}
  footer a {{ color:var(--accent); text-decoration:none; }}

  /* ─── RESPONSIVE ─── */
  @media (max-width:800px) {{ .stats {{ grid-template-columns:repeat(2,1fr); }} .grid {{ grid-template-columns:1fr; }} }}
  @media (max-width:500px) {{ .head-row {{ flex-direction:column; align-items:flex-start; }} .head-info {{ text-align:left; }} .flt-group {{ gap:4px; }} }}
</style>
</head>
<body>
<div class="container">

  <!-- HEADER -->
  <header>
    <div class="head-row">
      <div class="head-logo">
        <div class="icon">◈</div>
        <h1><span>Datagateway</span></h1>
      </div>
      <div class="head-info">
        <div>OSINT News Dashboard</div>
        <div style="margin-top:2px">{last_update} · {total_count} articles · {source_count} sources</div>
      </div>
    </div>
  </header>

  <!-- STATS -->
  <div class="stats">
    {stats_html}
  </div>

  <!-- SEARCH -->
  <div class="toolbar">
    <input class="srch" id="srch" type="text" placeholder="Search titles, sources, excerpts..." oninput="applyFilters()">
  </div>

  <!-- FILTERS -->
  <div class="flt-group">
    <span class="flt-glabel">Source</span>
    <button class="flt flt-clear on" data-g="source" data-v="all" onclick="clearGroup('source')">All</button>
    {source_btns}
  </div>
  <div class="flt-group">
    <span class="flt-glabel">Category</span>
    <button class="flt flt-clear on" data-g="cat" data-v="all" onclick="clearGroup('cat')">All</button>
    {cat_btns}
  </div>
  <div class="flt-group" style="margin-bottom:20px">
    <span class="flt-glabel">Language</span>
    <button class="flt flt-clear on" data-g="lang" data-v="all" onclick="clearGroup('lang')">All</button>
    {lang_btns}
  </div>

  <!-- GRID -->
  <div class="grid" id="grid">
    {cards_html}
  </div>

  <div class="no-r" id="noR">No articles match your filters.</div>

  <!-- VIEWBOX -->
  {viewbox_html}

  <!-- FOOTER -->
  <footer>
    Datagateway — OSINT Aggregator · Daily fetch 07:00 &amp; 18:00 WIB ·
    <a href="https://github.com/jtoemion/Datagateway" target="_blank">github.com/jtoemion/Datagateway</a>
  </footer>

</div>

<script>
// ─── Filter state ───
const state = {{ source:'all', cat:'all', lang:'all', search:'' }};

function toggleFilter(btn, group) {{
  const val = btn.dataset.v;
  if (val === 'all') {{ clearGroup(group); return; }}
  state[group] = state[group] === val ? 'all' : val;
  renderGroup(group);
  applyFilters();
}}

function clearGroup(group) {{
  state[group] = 'all';
  renderGroup(group);
  applyFilters();
}}

function renderGroup(group) {{
  document.querySelectorAll(`.flt[data-g="${{group}}"]`).forEach(b => {{
    const v = b.dataset.v;
    b.classList.toggle('on', state[group] === v || (v === 'all' && state[group] === 'all'));
  }});
}}

function applyFilters() {{
  const q = (document.getElementById('srch').value || '').toLowerCase();
  state.search = q;
  const cards = document.querySelectorAll('.card');
  let visible = 0;
  cards.forEach(c => {{
    const s = c.dataset.source; const ct = c.dataset.cat; const l = c.dataset.lang;
    const ok = (state.source==='all'||s===state.source)
           && (state.cat==='all'||ct===state.cat)
           && (state.lang==='all'||l===state.lang);
    const txt = (c.querySelector('.card-title')?.textContent||'').toLowerCase()
              + ' ' + (c.querySelector('.card-excerpt')?.textContent||'').toLowerCase()
              + ' ' + s.toLowerCase();
    const match = !q || txt.includes(q);
    if (ok && match) {{ c.style.display=''; visible++; }} else {{ c.style.display='none'; }}
  }});
  document.getElementById('noR').classList.toggle('show', visible===0);
}}

// ─── Copy wikilink ───
function copyWiki(el) {{
  const code = el.querySelector('.wiki-link');
  const txt = code.textContent.trim();
  navigator.clipboard.writeText(txt).then(() => {{
    el.classList.add('copied');
    const lbl = el.querySelector('.wiki-copy');
    const orig = lbl.textContent;
    lbl.textContent = 'copied!';
    setTimeout(() => {{ lbl.textContent=orig; el.classList.remove('copied'); }}, 1200);
  }}).catch(() => {{}});
}}

// ─── Viewbox (show .md content) ───
let viewMeta = {{}};

function openViewbox(filePath) {{
  // We store metadata in data attributes or fetch via a simple approach:
  // For now, show the wikilink and metadata of the article.
  const card = event?.target?.closest?.('.card');
  if (!card) return;
  const title = card.querySelector('.card-title')?.textContent || '';
  const source = card.querySelector('.card-source')?.textContent || '';
  const date = card.querySelector('.card-date')?.textContent || '';
  const wikilink = card.querySelector('.wiki-link')?.textContent || '';
  const id = card.querySelector('.meta-id')?.textContent || '';
  const cat = card.querySelector('.meta-cat')?.textContent || '';
  const url = card.querySelector('.act-ext')?.getAttribute('href') || '';

  document.getElementById('viewbox-body').innerHTML = `
    <div style="font-size:13px;color:var(--text-muted);margin-bottom:12px">
      source: <strong>${{source}}</strong> · category: ${{cat}} · id: ${{id}}
    </div>
    <div style="margin-bottom:12px">
      <code style="background:var(--surface-2);padding:4px 8px;border-radius:4px;font-size:13px">${{wikilink}}</code>
    </div>
    <div style="margin-bottom:16px">
      <a href="${{url}}" target="_blank" class="act act-ext" style="display:inline-flex">Open Original →</a>
    </div>
    <hr style="border:none;border-top:1px solid var(--border);margin:12px 0">
    <div style="font-size:14px;font-weight:600;margin-bottom:8px">${{title}}</div>
    <div style="font-size:12px;color:var(--text-muted)">${{date}}</div>
  `;
  document.getElementById('viewbox').classList.add('show');
}}

function closeViewbox(e) {{
  if (!e || e.target === e.currentTarget) {{
    document.getElementById('viewbox').classList.remove('show');
  }}
}}

// ─── Keyboard shortcut ───
document.addEventListener('keydown', e => {{
  if (e.key==='Escape') closeViewbox();
}});
</script>
</body>
</html>"""
    return html


def main():
    print(f"Datagateway — Build Dashboard v2 ({datetime.now(WIB).strftime('%Y-%m-%d %H:%M WIB')})")
    print("=" * 60)

    articles = collect_articles()
    print(f"  Collected: {len(articles)} articles")

    html = build_html(articles)

    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
    outpath = DASHBOARD_DIR / "index.html"
    outpath.write_text(html, encoding="utf-8")
    print(f"  Dashboard: {outpath} ({len(html)} bytes)")

    print(f"\n{'=' * 60}")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
