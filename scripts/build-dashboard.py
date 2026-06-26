#!/usr/bin/env python3
"""
Datagateway — Dashboard Builder v3
Baca dari SQLite (cepat, tanpa parse ulang .md).
Card profesional, wikilinks, metadata, filter 3-axis.
"""

import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from scripts.database import (
    init_db,
    get_articles,
    get_article_count,
    get_today_count,
    get_source_stats,
    get_category_stats,
    get_latest_date,
)

WIB = timezone(timedelta(hours=7))
REPO_ROOT = Path(__file__).resolve().parent.parent
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
DEFAULT_COLOR = ("#58a6ff", "#58a6ff33")

SOURCE_GLYPH = {
    "CNN Indonesia": "C", "Detik": "D", "CNBC Indonesia": "B",
    "Antara": "A", "Republika": "R", "BBC Indonesia": "B",
    "BBC News": "B", "NY Times": "N",
}


def esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def build_html(articles: list[dict]) -> str:
    now = datetime.now(WIB)
    today_count = get_today_count()
    total_count = get_article_count()
    source_stats = get_source_stats()
    cat_stats = get_category_stats()
    source_count = len(source_stats)
    last_update = now.strftime("%Y-%m-%d %H:%M WIB")
    latest_date = get_latest_date()

    # ── STATS ──
    stats_html = f"""
    <div class="stat-card"><div class="num">{today_count}</div><div class="stat-label">Today</div></div>
    <div class="stat-card"><div class="num">{total_count}</div><div class="stat-label">Total Articles</div></div>
    <div class="stat-card"><div class="num">{source_count}</div><div class="stat-label">Sources</div></div>
    <div class="stat-card"><div class="num">{latest_date}</div><div class="stat-label">Latest</div></div>"""

    # ── FILTER BUTTONS ──
    def btn(text, count, filter_val, group="source"):
        return f"""<button class="flt" data-g="{group}" data-v="{esc(filter_val)}" onclick="toggleFilter(this,'{group}')">{esc(text)} <span class="flt-c">{count}</span></button>"""

    source_btns = "\n      ".join(
        btn(s["source"], s["count"], s["source"]) for s in source_stats
    )
    cat_btns = "\n      ".join(
        btn(c["category"].title(), c["count"], c["category"], "cat") for c in cat_stats
    )

    # ── CARDS ──
    cards_html = ""
    for a in articles:
        src = a.get("source", "")
        fg, bg = SOURCE_COLORS.get(src, DEFAULT_COLOR)
        glyph = SOURCE_GLYPH.get(src, src[0].upper() if src else "?")
        date_short = a.get("date_wib") or a.get("date", "")[:10]
        cat = a.get("category", "—").title()
        title_esc = esc(a.get("title", "?"))
        excerpt_esc = esc(a.get("excerpt", "")[:350])
        wikilink_esc = esc(a.get("wikilink", ""))
        url_esc = esc(a.get("url", ""))
        filepath = a.get("filepath", "")
        md_path = f"file://{esc(str(REPO_ROOT / filepath))}" if filepath else ""

        cards_html += f"""
    <article class="card" data-source="{esc(src)}" data-cat="{a.get('category','')}" data-lang="{a.get('lang','')}">
      <div class="card-accent" style="background:{fg}"></div>
      <div class="card-body">
        <div class="card-top">
          <span class="card-glyph" style="background:{bg};color:{fg};border-color:{fg}">{glyph}</span>
          <span class="card-source" style="color:{fg}">{esc(src)}</span>
          <span class="card-lang badge-{a.get('lang','id')}">{a.get('lang','id')}</span>
          <span class="card-date">{date_short}</span>
        </div>
        <a href="{url_esc}" target="_blank" rel="noopener" class="card-title">{title_esc}</a>
        <p class="card-excerpt">{excerpt_esc}</p>
        <div class="card-meta">
          <span class="meta-cat">{cat}</span>
          <span class="meta-id">{a.get('id','')}</span>
        </div>
        <div class="card-wiki" onclick="copyWiki(this)" title="Click to copy wikilink">
          <span class="wiki-label">wikilink</span>
          <code class="wiki-link">{wikilink_esc}</code>
          <span class="wiki-copy">copy</span>
        </div>
        <div class="card-actions">
          <a href="{url_esc}" target="_blank" rel="noopener" class="act act-ext">Open Original →</a>
          {f'<a href="{md_path}" class="act act-md">📄 .md</a>' if md_path else ''}
        </div>
      </div>
    </article>"""

    # ── FULL HTML ──
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

  header {{ padding:28px 0 16px; border-bottom:1px solid var(--border); margin-bottom:24px; }}
  .head-row {{ display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:12px; }}
  .head-logo {{ display:flex; align-items:center; gap:14px; }}
  .head-logo .icon {{ width:40px; height:40px; border-radius:10px; background:linear-gradient(135deg,#60a5fa,#4ade80); display:flex; align-items:center; justify-content:center; font-size:20px; font-weight:700; color:#0b0f15; }}
  .head-logo h1 {{ font-size:24px; font-weight:700; letter-spacing:-0.5px; }}
  .head-logo h1 span {{ background:linear-gradient(135deg,var(--accent),var(--green)); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }}
  .head-info {{ text-align:right; font-size:13px; color:var(--text-muted); line-height:1.5; }}

  .stats {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin-bottom:24px; }}
  .stat-card {{ background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); padding:16px; text-align:center; }}
  .stat-card .num {{ font-size:30px; font-weight:700; color:var(--accent); line-height:1.2; }}
  .stat-card .stat-label {{ font-size:11px; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.5px; margin-top:2px; }}

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

  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(340px,1fr)); gap:14px; margin-bottom:28px; }}

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

  .no-r {{ display:none; text-align:center; padding:60px 20px; color:var(--text-muted); grid-column:1/-1; }}
  .no-r.show {{ display:block; }}

  footer {{ border-top:1px solid var(--border); padding:20px 0; margin-top:12px; text-align:center; font-size:12px; color:var(--text-muted); }}
  footer a {{ color:var(--accent); text-decoration:none; }}

  @media (max-width:800px) {{ .stats {{ grid-template-columns:repeat(2,1fr); }} .grid {{ grid-template-columns:1fr; }} }}
  @media (max-width:500px) {{ .head-row {{ flex-direction:column; align-items:flex-start; }} .head-info {{ text-align:left; }} }}
</style>
</head>
<body>
<div class="container">
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

  <div class="stats">{stats_html}</div>

  <div class="toolbar">
    <input class="srch" id="srch" type="text" placeholder="Search titles, sources, excerpts..." oninput="applyFilters()">
  </div>

  <div class="flt-group">
    <span class="flt-glabel">Source</span>
    <button class="flt flt-clear on" data-g="source" data-v="all" onclick="clearGroup('source')">All</button>
    {source_btns}
  </div>
  <div class="flt-group" style="margin-bottom:20px">
    <span class="flt-glabel">Category</span>
    <button class="flt flt-clear on" data-g="cat" data-v="all" onclick="clearGroup('cat')">All</button>
    {cat_btns}
  </div>

  <div class="grid" id="grid">{cards_html}</div>
  <div class="no-r" id="noR">No articles match your filters.</div>

  <footer>
    Datagateway — OSINT Aggregator · Daily fetch 07:00 &amp; 18:00 WIB ·
    <a href="https://github.com/jtoemion/Datagateway" target="_blank">github.com/jtoemion/Datagateway</a>
  </footer>
</div>

<script>
const state = {{ source:'all', cat:'all', search:'' }};

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
    const s = c.dataset.source; const ct = c.dataset.cat;
    const ok = (state.source==='all'||s===state.source) && (state.cat==='all'||ct===state.cat);
    const txt = (c.querySelector('.card-title')?.textContent||'').toLowerCase()
              + ' ' + (c.querySelector('.card-excerpt')?.textContent||'').toLowerCase()
              + ' ' + (c.querySelector('.card-source')?.textContent||'').toLowerCase();
    const match = !q || txt.includes(q);
    if (ok && match) {{ c.style.display=''; visible++; }} else {{ c.style.display='none'; }}
  }});
  document.getElementById('noR').classList.toggle('show', visible===0);
}}

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
</script>
</body>
</html>"""
    return html


def main():
    init_db()
    print(f"Datagateway — Build Dashboard v3 ({datetime.now(WIB).strftime('%Y-%m-%d %H:%M WIB')})")
    print("=" * 60)

    total = get_article_count()
    articles = get_articles(limit=200)
    print(f"  DB: {total} total articles, fetching {len(articles)} for dashboard")

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
