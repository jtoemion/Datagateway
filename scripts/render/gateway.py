"""
Datagateway — Render Gateway (GATEWAY)
Orchestrates dashboard assembly: merges render modules with article viewer data.
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
WIB = timezone(timedelta(hours=7))

sys.path.insert(0, str(REPO_ROOT))

from scripts.database import (
    get_articles, get_article_count, get_today_count,
    get_source_stats, get_category_stats, get_latest_date,
    get_scraped_article, get_football_events, get_football_odds,
    get_football_count, get_next_football_match,
)
from scripts.render.news import build_world_news_html
from scripts.render.football import build_football_html
from scripts.search.corpus import build_corpus_json, build_synonym_json


def build_index_html(articles: list[dict]) -> str:
    """Assemble the full dashboard index.html."""
    source_count = len(get_source_stats())
    total_count = get_article_count()
    last_update = datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB")
    latest_date = get_latest_date()
    today_count = get_today_count()

    fb_news = [a for a in articles if a.get("category") == "football"]
    fb_count_news = len(fb_news)

    news_tab = build_world_news_html(articles)
    football_tab = build_football_html(fb_news)

    # Corpus + synonym JSON
    corpus_json = build_corpus_json(articles)
    synonym_json = build_synonym_json()

    # Determine header title
    title = "Datagateway"
    if fb_count_news:
        title += f" \u2022 {total_count} articles, {fb_count_news} football"

    # Read the CSS/JS template from the existing build
    css = _read_styles()
    gsap_js = _read_gsap_js()

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>{title}</title>
<style>{css}</style>
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/ScrollTrigger.min.js"></script>
</head>
<body>
<div class="container">

<header>
  <div class="head-row">
    <div class="head-logo">
      <span class="icon">DG</span>
      <div>
        <h1>Datagateway</h1>
        <div class="head-info">{last_update} \u00b7 {total_count} articles \u00b7 {source_count} sources{f' \u00b7 \u26bd {fb_count_news} football' if fb_count_news else ''}</div>
      </div>
    </div>
  </div>
</header>

<div class="tabs" role="tablist">
  <div class="tab active" data-tab="news" onclick="switchTab('news')">World News</div>
  <div class="tab" data-tab="football" onclick="switchTab('football')">Football <small>{get_football_count()}</small></div>
  <div class="tab" data-tab="more" onclick="switchTab('more')">More \u25b8</div>
</div>

<div class="tab-pane active" id="tab-news">{news_tab}</div>

<div class="tab-pane" id="tab-football">{football_tab}</div>

<div class="tab-pane" id="tab-more">
  <div style="padding:40px;text-align:center;color:var(--text-muted)">
    <h3 style="margin:0 0 12px;color:var(--text)">Coming Soon</h3>
    <p>Entity profiles, knowledge graph, Hermes analysis briefings.</p>
  </div>
</div>

<footer>Datagateway \u00b7 OSINT Daily Briefing \u00b7 <a href="https://github.com/jtoemion/Datagateway" target="_blank">GitHub</a></footer>

</div>

<!-- Embedded search data -->
<script type="application/json" id="corpus-data">{corpus_json}</script>
<script type="application/json" id="synonym-data">{synonym_json}</script>

<script>
{gsap_js}
{_read_client_js()}
</script>
</body>
</html>"""


def _read_styles() -> str:
    """Extract CSS from the existing build-dashboard.py template."""
    # For now, return the inline CSS that was in build-dashboard.py
    # This is a placeholder — refactored in later phases
    return _INLINE_CSS


def _read_gsap_js() -> str:
    return _GSAP_ANIMATIONS_JS


def _read_client_js() -> str:
    return _CLIENT_JS


# ─── Inline CSS (from existing build-dashboard.py) ──────────────────────────────

_INLINE_CSS = """
:root {
  --bg: #0a0a0f; --surface: #141420; --surface-hover: #1c1c2e;
  --border: #2a2a3e; --text: #e8e8f0; --text-muted: #7a7a8e;
  --accent: #6366f1; --radius: 12px;
  --font: 'Inter', system-ui, -apple-system, sans-serif;
  --font-size: 14px;
}
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:var(--text); font-family:var(--font); font-size:var(--font-size); line-height:1.5; -webkit-font-smoothing:antialiased; }
.container { max-width:1280px; margin:0 auto; padding:0 24px; }

/* Header */
header { padding:24px 0 16px; }
.head-row { display:flex; align-items:center; justify-content:space-between; gap:16px; }
.head-logo { display:flex; align-items:center; gap:14px; }
.head-logo .icon { width:40px; height:40px; border-radius:10px; background:linear-gradient(135deg,#6366f1,#a855f7); display:flex; align-items:center; justify-content:center; font-weight:800; font-size:14px; color:#fff; flex-shrink:0; }
.head-logo h1 { font-size:22px; font-weight:700; letter-spacing:-0.3px; margin:0; }
.head-info { font-size:12px; color:var(--text-muted); margin-top:2px; }

/* Tabs */
.tabs { display:flex; gap:2px; border-bottom:1px solid var(--border); margin-bottom:20px; overflow-x:auto; }
.tab { padding:12px 20px; cursor:pointer; font-size:13px; font-weight:600; color:var(--text-muted); border-bottom:2px solid transparent; transition:all .15s; white-space:nowrap; user-select:none; }
.tab:hover { color:var(--text); }
.tab.active { color:var(--accent); border-bottom-color:var(--accent); }
.tab-pane { display:none; }
.tab-pane.active { display:block; }

/* Stats */
.stats { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:20px; }
.stat-card { background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); padding:16px; text-align:center; }
.stat-card .num { font-size:28px; font-weight:800; color:var(--accent); line-height:1; }
.stat-card .stat-label { font-size:11px; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.5px; margin-top:4px; }

/* Toolbar */
.toolbar { display:flex; flex-direction:column; gap:10px; margin-bottom:16px; }
.srch { width:100%; padding:10px 14px; border:1px solid var(--border); border-radius:8px; background:var(--surface); color:var(--text); font-size:13px; outline:none; transition:border .15s; }
.srch:focus { border-color:var(--accent); }
.flt-group { display:flex; align-items:flex-start; gap:8px; }
.flt-glabel { font-size:10px; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.5px; padding-top:4px; min-width:48px; }
.flt-row { display:flex; flex-wrap:wrap; gap:4px; }
.flt { padding:4px 10px; border:1px solid var(--border); border-radius:6px; background:var(--surface); color:var(--text-muted); font-size:11px; cursor:pointer; transition:all .15s; }
.flt:hover { border-color:var(--accent); color:var(--text); }
.flt.active { background:var(--accent); border-color:var(--accent); color:#fff; }

/* Grid */
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(340px,1fr)); gap:14px; }
.card { display:flex; flex-direction:column; background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); overflow:hidden; transition:transform .15s,box-shadow .15s; position:relative; }
.card:hover { transform:translateY(-2px); box-shadow:0 8px 30px rgba(0,0,0,.3); }
.card-accent { position:absolute; top:0; left:0; width:4px; height:100%; }
.card-accent span { position:absolute; top:10px; left:-4px; width:22px; height:22px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:10px; font-weight:700; color:#fff; }
.card-img { width:100%; height:160px; overflow:hidden; }
.card-img img { width:100%; height:100%; object-fit:cover; transition:transform .3s; }
.card:hover .card-img img { transform:scale(1.03); }
.card-body { padding:14px 16px 10px; flex:1; }
.card-meta-top { display:flex; align-items:center; gap:8px; margin-bottom:8px; font-size:11px; }
.card-source { font-weight:700; font-size:11px; text-transform:uppercase; letter-spacing:0.3px; }
.card-lang { font-size:9px; background:var(--border); padding:1px 5px; border-radius:3px; color:var(--text-muted); }
.card-date { color:var(--text-muted); }
.card-readtime { color:var(--text-muted); }
.card-title { font-size:15px; font-weight:600; line-height:1.4; color:var(--text); text-decoration:none; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; margin-bottom:6px; }
.card-title:hover { color:var(--accent); }
.card-excerpt { font-size:13px; color:var(--text-muted); line-height:1.5; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; margin-bottom:8px; }
.card-meta { display:flex; align-items:center; justify-content:space-between; }
.card-cat { font-size:10px; text-transform:uppercase; letter-spacing:0.3px; color:var(--text-muted); background:var(--border); padding:1px 6px; border-radius:3px; }
.card-footer-actions { padding:0 16px 12px; display:flex; flex-direction:column; gap:8px; }
.wiki-wrapper { display:flex; align-items:center; gap:6px; }
.wiki-label { font-size:9px; text-transform:uppercase; letter-spacing:0.5px; color:var(--text-muted); font-weight:600; }
.wiki-link { font-size:10px; color:var(--accent); background:var(--bg); padding:2px 8px; border-radius:4px; font-family:mono; }
.wiki-copy { font-size:9px; padding:2px 8px; border:1px solid var(--border); border-radius:4px; background:var(--surface); color:var(--text-muted); cursor:pointer; }
.wiki-copy.copied { background:#4ade8022; }
.card-actions { display:flex; gap:6px; }
.act { padding:4px 12px; border:1px solid var(--border); border-radius:6px; font-size:11px; color:var(--text-muted); text-decoration:none; transition:all .12s; cursor:pointer; background:var(--surface); display:inline-flex; align-items:center; gap:4px; min-height:28px; }
.act:hover { border-color:var(--accent); color:var(--accent); }

/* Football */
.hero-card { background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); overflow:hidden; margin-bottom:20px; }
.hero-content { padding:24px 24px; }
.hero-meta-top { display:flex; align-items:center; gap:10px; margin-bottom:16px; font-size:12px; color:var(--text-muted); }
.hero-badge { font-size:11px; font-weight:700; padding:3px 10px; border-radius:6px; text-transform:uppercase; letter-spacing:0.5px; }
.cs-sched { background:#6366f122; color:#6366f1; }
.cs-ft { background:#ef444422; color:#ef4444; }
.hero-season { font-weight:500; }
.hero-date { }
.hero-match { display:flex; align-items:center; justify-content:space-between; gap:32px; margin-bottom:16px; }
.hero-team { display:flex; flex-direction:column; align-items:center; gap:6px; min-width:120px; }
.hero-team .flag-icon { width:36px; height:auto; border-radius:2px; }
.ht-abbr { font-size:28px; font-weight:800; letter-spacing:-1px; }
.ht-name { font-size:14px; color:var(--text); font-weight:500; }
.ht-score { font-size:32px; font-weight:900; }
.ht-vs { color:var(--text-muted); font-size:14px; text-transform:uppercase; letter-spacing:1px; }
.hero-venue { font-size:12px; color:var(--text-muted); display:flex; align-items:center; gap:6px; flex-wrap:wrap; }
.venue-icon { }
.hero-odds-label { font-size:12px; font-weight:600; color:var(--text); margin-top:16px; margin-bottom:8px; }
.odds-book { max-width:400px; }
.odds-row { display:grid; grid-template-columns:1fr 60px 60px 60px; padding:4px 0; font-size:13px; border-bottom:1px solid var(--border); }
.odds-header { font-size:10px; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.5px; padding-bottom:6px; }
.odds-name { color:var(--text); }
.odds-val { text-align:center; font-weight:600; font-variant-numeric:tabular-nums; }
.odds-empty { color:var(--text-muted); font-size:12px; }

/* Carousel */
.carousel-section { margin-bottom:28px; }
.carousel-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:14px; }
.carousel-header h3 { font-size:16px; font-weight:600; }
.carousel { display:flex; gap:12px; overflow-x:auto; scroll-snap-type:x mandatory; -webkit-overflow-scrolling:touch; padding-bottom:8px; }
.flag-icon { display:inline-block; width:20px; height:15px; vertical-align:middle; border-radius:2px; object-fit:cover; }
.cs-card { flex:0 0 220px; scroll-snap-align:start; background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:14px; position:relative; transition:border .15s; }
.cs-card:hover { border-color:var(--accent); }
.cs-badge { font-size:9px; font-weight:700; padding:2px 8px; border-radius:4px; display:inline-block; margin-bottom:8px; }
.cs-abbr { font-weight:700; display:inline-flex; align-items:center; gap:4px; font-size:16px; }
.cs-vs { color:var(--text-muted); font-size:12px; }
.cs-info { font-size:11px; color:var(--text-muted); margin-top:6px; }
.cs-small { font-size:10px; }
.cs-odds { margin-top:8px; font-size:12px; font-weight:600; color:var(--accent); }
.fb-news-section { margin-top:24px; padding-top:20px; border-top:1px solid var(--border); }
.fb-news-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:14px; }
.fb-news-header h3 { font-size:16px; font-weight:600; margin:0; }
.fb-card .card-accent { background:#00b050 !important; }
.fb-card .card-accent span { display:none; }

/* Footer */
footer { border-top:1px solid var(--border); padding:20px 0; margin-top:12px; text-align:center; font-size:12px; color:var(--text-muted); }
footer a { color:var(--accent); text-decoration:none; }

/* Responsive */
@media (max-width:1024px) {
  .container { padding:0 16px; }
  .grid { grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); }
  .hero-match { gap:24px; }
  .hero-team { min-width:100px; }
  .odds-book { font-size:12px; }
}
@media (max-width:640px) {
  header { padding:16px 0; }
  .head-logo h1 { font-size:18px; }
  .head-logo .icon { width:32px; height:32px; font-size:12px; }
  .stats { grid-template-columns:repeat(2,1fr); }
  .stats .num { font-size:24px; }
  .grid { grid-template-columns:1fr; }
  .tab { padding:10px 14px; font-size:11px; }
  .card-title { font-size:14px; }
  .card-excerpt { font-size:12px; }
  .hero-match { flex-direction:column; gap:16px; }
  .ht-abbr { font-size:24px; }
  .odds-row { grid-template-columns:1fr 40px 40px 40px; font-size:11px; }
  .flt { padding:4px 8px; font-size:10px; }
  .flt-group .flt-glabel { font-size:9px; min-width:36px; }
  .fb-news-section { margin-top:16px; padding-top:16px; }
  .head-info { font-size:11px; }
  .tabs { overflow-x:auto; }
  .tab { padding:8px 10px; white-space:nowrap; }
  .hero-content { padding:20px 16px; }
  .odds-book { grid-template-columns:1fr 50px 50px 50px; font-size:12px; }
}
@media (max-width:420px) {
  .container { padding:0 10px; }
  header { padding:12px 0; }
  .head-logo h1 { font-size:16px; }
  .head-logo { gap:8px; }
  .stats { gap:6px; }
  .stat-card { padding:10px; }
  .grid { gap:10px; }
  .card-body { padding:10px 12px; }
  .card-meta .card-id { display:none; }
  .hero-content { padding:16px 12px; }
  .hero-meta-top { flex-wrap:wrap; gap:6px; }
  .hero-badge { font-size:9px; }
  .ht-abbr { font-size:20px; }
  .ht-name { font-size:12px; }
  .carousel { gap:8px; }
  .cs-card { flex:0 0 160px; padding:10px; }
  .card-footer-actions { padding:0 12px 10px; }
  .act { padding:4px 8px; font-size:10px; }
}
"""

_GSAP_ANIMATIONS_JS = """
gsap.from('.stat-card',{duration:.4,scale:.8,opacity:0,stagger:.08,ease:'back.out(1.4)'});
gsap.from('.tab',{duration:.3,opacity:0,y:-6,stagger:.05,ease:'power2.out'});
gsap.from('.card',{duration:.4,y:20,opacity:0,stagger:{each:.03,from:'random'},ease:'power2.out'});
"""

_CLIENT_JS = """
function switchTab(name) {
  document.querySelectorAll('.tab-pane').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  const pane = document.getElementById('tab-' + name);
  const tab = document.querySelector(`.tab[data-tab="${name}"]`);
  if(pane) pane.classList.add('active');
  if(tab) tab.classList.add('active');
  // Re-trigger GSAP on pane
  const cards = pane?.querySelectorAll('.card');
  if(cards && cards.length) {
    gsap.from(cards,{duration:.3,y:12,opacity:0,stagger:{each:.02,from:'random'},ease:'power2.out',clearProps:'all'});
  }
}

function applyFilters() {
  const search = (document.getElementById('search')?.value || '').toLowerCase();
  const activeSrc = document.querySelector('.flt-src.active')?.dataset?.filter || 'all';
  const activeCat = document.querySelector('.flt-cat.active')?.dataset?.filter || 'all';
  const corpus = document.getElementById('corpus-data');
  const synData = document.getElementById('synonym-data');
  let synonyms = {};
  try { if(synData) synonyms = JSON.parse(synData.textContent); } catch(e) {}

  document.querySelectorAll('.card').forEach(card => {
    const title = card.querySelector('.card-title')?.textContent?.toLowerCase() || '';
    const excerpt = card.querySelector('.card-excerpt')?.textContent?.toLowerCase() || '';
    const source = card.querySelector('.card-source')?.textContent?.toLowerCase() || '';
    const cat = card.querySelector('.card-cat')?.textContent?.toLowerCase() || '';
    const id = card.dataset?.id || '';

    let match = true;

    // Source filter
    if(activeSrc !== 'all' && !source.includes(activeSrc.toLowerCase())) match = false;

    // Category filter
    if(activeCat !== 'all' && !cat.includes(activeCat.toLowerCase())) match = false;

    // Search
    if(search) {
      const text = title + ' ' + excerpt + ' ' + source + ' ' + id;
      const expanded = [search];
      for(const [key,values] of Object.entries(synonyms)) {
        if(search.includes(key) || values.some(v=>search.includes(v))) {
          expanded.push(key, ...values);
        }
      }
      match = expanded.some(t => text.includes(t));
    }

    card.style.display = match ? '' : 'none';
  });
}

// Source and category filter click handlers
document.addEventListener('click', function(e) {
  const btn = e.target.closest('.flt');
  if(!btn) return;

  const group = btn.classList.contains('flt-src') ? 'flt-src' : 'flt-cat';
  document.querySelectorAll('.' + group).forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  applyFilters();
});
"""


def build_dashboard(articles: list[dict] = None) -> str:
    """Main entry point: build and write index.html."""
    if articles is None:
        articles = get_articles(limit=500)
    html = build_index_html(articles)
    output_path = REPO_ROOT / "dashboard" / "index.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return str(output_path)


if __name__ == "__main__":
    from scripts.database import init_db
    init_db()
    articles = get_articles(limit=500)
    path = build_dashboard(articles)
    print(f"  Dashboard: {path}")
