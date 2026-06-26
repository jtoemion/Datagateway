#!/usr/bin/env python3
"""
Datagateway — Dashboard Builder v4
Tabs: World News | Football | More
Football tab: hero card + match carousel with odds.
World News: cards with wikilinks + filters (same as v3).
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
    get_football_events,
    get_football_odds,
    get_football_count,
    get_next_football_match,
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


def format_odds(price: int) -> str:
    """Format American odds with +/- sign."""
    if price is None:
        return "—"
    if price > 0:
        return f"+{price}"
    return str(price)


def format_dt(dt_str: str) -> str:
    """2026-06-26T19:00:00Z → readable."""
    if not dt_str:
        return ""
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.astimezone(WIB).strftime("%a, %d %b %H:%M WIB")
    except Exception:
        return dt_str[:16]


def build_world_news_html(articles: list[dict]) -> str:
    """Build World News tab content (same as v3 but without outer layout)."""
    source_stats = get_source_stats()
    cat_stats = get_category_stats()
    today_count = get_today_count()
    total_count = get_article_count()

    # Stats
    stats = f"""
    <div class="stat-card"><div class="num">{today_count}</div><div class="stat-label">Today</div></div>
    <div class="stat-card"><div class="num">{total_count}</div><div class="stat-label">Total</div></div>
    <div class="stat-card"><div class="num">{len(source_stats)}</div><div class="stat-label">Sources</div></div>
    <div class="stat-card"><div class="num">{get_latest_date()}</div><div class="stat-label">Latest</div></div>"""

    def btn(text, count, val, group="source"):
        return f"""<button class="flt" data-g="{group}" data-v="{esc(val)}" onclick="toggleFilter(this,'{group}')">{esc(text)} <span class="flt-c">{count}</span></button>"""

    src_btns = "\n      ".join(btn(s["source"], s["count"], s["source"]) for s in source_stats)
    cat_btns = "\n      ".join(btn(c["category"].title(), c["count"], c["category"], "cat") for c in cat_stats)

    cards = ""
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
        fp = a.get("filepath", "")
        md_path = f"file://{esc(str(REPO_ROOT / fp))}" if fp else ""

        cards += f"""
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

    return f"""
<div class="tab-pane active" id="tab-news">
  <div class="stats">{stats}</div>
  <div class="toolbar">
    <input class="srch" id="srch" type="text" placeholder="Search titles, sources, excerpts..." oninput="applyFilters()">
  </div>
  <div class="flt-group">
    <span class="flt-glabel">Source</span>
    <button class="flt flt-clear on" data-g="source" data-v="all" onclick="clearGroup('source')">All</button>
    {src_btns}
  </div>
  <div class="flt-group" style="margin-bottom:20px">
    <span class="flt-glabel">Category</span>
    <button class="flt flt-clear on" data-g="cat" data-v="all" onclick="clearGroup('cat')">All</button>
    {cat_btns}
  </div>
  <div class="grid" id="grid">{cards}</div>
  <div class="no-r" id="noR">No articles match your filters.</div>
</div>"""


def build_football_html() -> str:
    """Build Football tab content — hero + carousel."""
    events = get_football_events()
    if not events:
        return '<div class="tab-pane" id="tab-football"><div class="empty-state">No football data yet. Run fetch-football.py.</div></div>'

    # Separate scheduled vs completed
    scheduled = [e for e in events if e.get("event_status") == "STATUS_SCHEDULED"]
    completed = [e for e in events if e.get("event_status") != "STATUS_SCHEDULED"]
    ordered = scheduled + completed

    next_match = scheduled[0] if scheduled else ordered[0]

    # ── Hero card ──
    def hero_card(match: dict) -> str:
        away = match.get("team_away", "?")
        home = match.get("team_home", "?")
        away_abbr = match.get("team_away_abbr", "")
        home_abbr = match.get("team_home_abbr", "")
        venue = match.get("venue_name", "")
        location = match.get("venue_location", "")
        broadcast = match.get("broadcast", "")
        dt_str = format_dt(match.get("event_date", ""))
        status = match.get("status_detail", "")

        score_away = match.get("score_away", 0)
        score_home = match.get("score_home", 0)
        is_live = match.get("event_status") == "STATUS_LIVE"
        is_ft = match.get("event_status") == "STATUS_FULL_TIME"

        # Score display
        if is_ft or is_live:
            score_html = f'<div class="hero-score"><span class="hs-away">{score_away}</span><span class="hs-colon">:</span><span class="hs-home">{score_home}</span></div>'
            status_label = "LIVE" if is_live else "FT"
            hero_cls = "hero-live" if is_live else "hero-ft"
            badge_html = f'<span class="hero-badge {hero_cls}">{status_label}</span>'
        else:
            score_html = f'<div class="hero-score"><span class="hs-away">{away_abbr}</span><span class="hs-colon">vs</span><span class="hs-home">{home_abbr}</span></div>'
            badge_html = f'<span class="hero-badge hero-scheduled">Up Next</span>'

        # Odds from DB — moneyline (market_id=1), main lines only
        eid = match["event_id"]
        odds_rows = get_football_odds(eid, market_id=1)
        main_lines = [o for o in odds_rows if o.get("is_main_line") == 1]

        odds_html = ""
        if main_lines:
            # Header
            odds_html += """
                <div class="odds-book ob-header">
                  <span class="ob-name">Sportsbook</span>
                  <span class="ob-cell ob-away-col">Away</span>
                  <span class="ob-cell ob-draw-col">Draw</span>
                  <span class="ob-cell ob-home-col">Home</span>
                </div>"""
            # Group by affiliate
            for aff_id in sorted(set(o["affiliate_id"] for o in main_lines)):
                entries = [o for o in main_lines if o["affiliate_id"] == aff_id]
                if not entries:
                    continue
                aff_name = entries[0].get("affiliate_name", f"Book {aff_id}")
                p_away = next((o for o in entries if o.get("participant_name") == away), None)
                p_home = next((o for o in entries if o.get("participant_name") == home), None)
                p_draw = next((o for o in entries if o.get("participant_type") == "RESULT" and o.get("participant_name","").lower() == "draw"), None)
                if p_away or p_home or p_draw:
                    odds_html += f"""
                <div class="odds-book">
                  <span class="ob-name">{aff_name}</span>
                  <span class="ob-cell ob-away-cell">{p_away and format_odds(p_away['price_american']) or '—'}</span>
                  <span class="ob-cell ob-draw-cell">{p_draw and format_odds(p_draw['price_american']) or '—'}</span>
                  <span class="ob-cell ob-home-cell">{p_home and format_odds(p_home['price_american']) or '—'}</span>
                </div>"""
        else:
            odds_html = '<div class="odds-empty">No odds available</div>'

        return f"""
    <div class="hero-card">
      <div class="hero-bg"></div>
      <div class="hero-content">
        <div class="hero-meta-top">
          {badge_html}
          <span class="hero-season">{match.get("season_type","FIFA World Cup")}</span>
          <span class="hero-date">{dt_str}</span>
        </div>
        <div class="hero-match">
          <div class="hero-team hero-away">
            <span class="ht-abbr">{away_abbr}</span>
            <span class="ht-name">{away}</span>
          </div>
          {score_html}
          <div class="hero-team hero-home">
            <span class="ht-abbr">{home_abbr}</span>
            <span class="ht-name">{home}</span>
          </div>
        </div>
        <div class="hero-venue">
          <span class="venue-icon">📍</span>
          {esc(venue)} — {esc(location)} · <strong>{esc(broadcast)}</strong>
        </div>
        {f'<div class="hero-odds-label">Moneyline Odds</div>' if main_lines else ''}
        {odds_html if main_lines else ''}
      </div>
    </div>"""

    # ── Carousel ──
    def carousel_card(match: dict) -> str:
        away = match.get("team_away", "?")
        home = match.get("team_home", "?")
        away_abbr = match.get("team_away_abbr", "")
        home_abbr = match.get("team_home_abbr", "")
        dt_short = format_dt(match.get("event_date", ""))
        venue = match.get("venue_name", "")
        broadcast = match.get("broadcast", "")
        status = match.get("status_detail", "")
        is_sched = match.get("event_status") == "STATUS_SCHEDULED"

        if is_sched:
            badge = f'<span class="cs-badge cs-sched">Scheduled</span>'
            score_line = f'<span class="cs-abbr">{away_abbr}</span><span class="cs-vs">vs</span><span class="cs-abbr">{home_abbr}</span>'
        else:
            sa, sh = match.get("score_away", 0), match.get("score_home", 0)
            badge = f'<span class="cs-badge cs-ft">FT</span>'
            score_line = f'<span class="cs-abbr">{away_abbr} {sa}</span><span class="cs-vs">:</span><span class="cs-abbr">{sh} {home_abbr}</span>'

        # Quick odds — show best price (favorite) moneyline
        odds_rows = get_football_odds(match["event_id"], market_id=1)
        main_lines = [o for o in odds_rows if o.get("is_main_line") == 1]
        ml = None
        if main_lines:
            # Pick the one with smallest price (most negative = favorite)
            best = min(main_lines, key=lambda o: abs(o.get("price_american", 0) or 0))
            ml = f'{esc(best.get("participant_name",""))} {format_odds(best["price_american"])}'

        return f"""
    <div class="cs-card">
      {badge}
      <div class="cs-match">{score_line}</div>
      <div class="cs-meta">
        <span>{esc(venue[:25])}</span>
        <span>{esc(broadcast)}</span>
      </div>
      <div class="cs-date">{dt_short}</div>
      {f'<div class="cs-odds">{esc(ml)}</div>' if ml else ''}
    </div>"""

    hero = hero_card(next_match)
    carousel = "\n".join(carousel_card(e) for e in ordered)

    return f"""
<div class="tab-pane" id="tab-football">
  {hero}
  <div class="carousel-section">
    <div class="carousel-header">
      <h3>All Matches</h3>
      <span class="carousel-count">{len(ordered)} events</span>
    </div>
    <div class="carousel" id="carousel">
      {carousel}
    </div>
  </div>
</div>"""


def build_html(articles: list[dict]) -> str:
    now = datetime.now(WIB)
    last_update = now.strftime("%Y-%m-%d %H:%M WIB")
    total_count = get_article_count()
    source_count = len(get_source_stats())
    fb_count = get_football_count()

    news_tab = build_world_news_html(articles)
    football_tab = build_football_html()

    return f"""<!DOCTYPE html>
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
  header {{ padding:28px 0 16px; border-bottom:1px solid var(--border); margin-bottom:0; }}
  .head-row {{ display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:12px; }}
  .head-logo {{ display:flex; align-items:center; gap:14px; }}
  .head-logo .icon {{ width:40px; height:40px; border-radius:10px; background:linear-gradient(135deg,#60a5fa,#4ade80); display:flex; align-items:center; justify-content:center; font-size:20px; font-weight:700; color:#0b0f15; }}
  .head-logo h1 {{ font-size:24px; font-weight:700; letter-spacing:-0.5px; }}
  .head-logo h1 span {{ background:linear-gradient(135deg,var(--accent),var(--green)); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }}
  .head-info {{ text-align:right; font-size:13px; color:var(--text-muted); line-height:1.5; }}

  /* ─── TABS ─── */
  .tabs {{ display:flex; gap:2px; border-bottom:2px solid var(--border); margin-bottom:24px; background:var(--surface); border-radius:0 0 var(--radius) var(--radius); padding:0 4px; }}
  .tab {{ padding:12px 24px; font-size:13px; font-weight:600; color:var(--text-muted); cursor:pointer; border-bottom:2px solid transparent; margin-bottom:-2px; transition:all .15s; user-select:none; position:relative; }}
  .tab:hover {{ color:var(--text); }}
  .tab.active {{ color:var(--accent); border-bottom-color:var(--accent); }}
  .tab .tab-badge {{ display:inline-flex; align-items:center; justify-content:center; min-width:18px; height:18px; background:var(--surface-2); border-radius:9px; padding:0 5px; font-size:10px; margin-left:6px; color:var(--text-muted); }}
  .tab.active .tab-badge {{ background:var(--accent); color:#0b0f15; }}
  .tab-more {{ opacity:.5; cursor:default !important; }}
  .tab-pane {{ display:none; }}
  .tab-pane.active {{ display:block; }}

  /* ─── WORLD NEWS STYLES ─── */
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

  /* ─── HERO CARD ─── */
  .hero-card {{ position:relative; border-radius:16px; overflow:hidden; margin-bottom:28px; background:linear-gradient(135deg,#1a2332,#0f1923); border:1px solid var(--border); }}
  .hero-bg {{ position:absolute; inset:0; background:radial-gradient(ellipse at 20% 50%, rgba(96,165,250,0.08) 0%, transparent 60%), radial-gradient(ellipse at 80% 50%, rgba(74,222,128,0.05) 0%, transparent 60%); }}
  .hero-content {{ position:relative; padding:28px 32px; }}
  .hero-meta-top {{ display:flex; align-items:center; gap:12px; margin-bottom:20px; flex-wrap:wrap; }}
  .hero-badge {{ display:inline-flex; padding:4px 12px; border-radius:20px; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:0.5px; }}
  .hero-scheduled {{ background:var(--accent); color:#0b0f15; }}
  .hero-live {{ background:var(--rose); color:#fff; animation:pulse 1.5s ease-in-out infinite; }}
  .hero-ft {{ background:var(--surface-2); color:var(--text-muted); }}
  @keyframes pulse {{ 0%,100% {{ opacity:1; }} 50% {{ opacity:.7; }} }}
  .hero-season {{ font-size:12px; color:var(--text-muted); }}
  .hero-date {{ margin-left:auto; font-size:13px; color:var(--text-muted); }}

  .hero-match {{ display:flex; align-items:center; justify-content:center; gap:40px; margin-bottom:20px; }}
  .hero-team {{ display:flex; flex-direction:column; align-items:center; gap:6px; min-width:140px; }}
  .ht-abbr {{ font-size:48px; font-weight:800; letter-spacing:-1px; line-height:1; }}
  .hero-away .ht-abbr {{ color:var(--accent); }}
  .hero-home .ht-abbr {{ color:var(--green); }}
  .ht-name {{ font-size:14px; color:var(--text); font-weight:500; }}
  .hero-score {{ display:flex; align-items:center; gap:12px; }}
  .hs-away,.hs-home {{ font-size:48px; font-weight:800; line-height:1; }}
  .hs-away {{ color:var(--accent); }}
  .hs-home {{ color:var(--green); }}
  .hs-colon {{ font-size:32px; font-weight:300; color:var(--text-muted); }}

  .hero-venue {{ display:flex; align-items:center; justify-content:center; gap:8px; font-size:13px; color:var(--text-muted); margin-bottom:16px; }}
  .hero-odds-label {{ font-size:11px; text-transform:uppercase; letter-spacing:0.5px; color:var(--text-muted); margin-bottom:8px; }}
  .odds-book {{ display:grid; grid-template-columns:1fr 60px 60px 60px; gap:8px; padding:8px 0; border-bottom:1px solid var(--border); font-size:13px; }}
  .odds-book:last-child {{ border-bottom:none; }}
  .ob-name {{ color:var(--text); font-weight:500; }}
  .ob-cell {{ text-align:center; font-family:monospace; font-weight:600; color:var(--amber); }}
  .ob-draw {{ color:var(--text-muted); }}
  .odds-empty {{ font-size:12px; color:var(--text-muted); padding:8px 0; }}

  /* ─── CAROUSEL ─── */
  .carousel-section {{ margin-bottom:28px; }}
  .carousel-header {{ display:flex; align-items:center; justify-content:space-between; margin-bottom:14px; }}
  .carousel-header h3 {{ font-size:16px; font-weight:600; }}
  .carousel-count {{ font-size:12px; color:var(--text-muted); }}
  .carousel {{ display:flex; gap:12px; overflow-x:auto; scroll-snap-type:x mandatory; padding-bottom:8px; }}
  .carousel::-webkit-scrollbar {{ height:4px; }}
  .carousel::-webkit-scrollbar-track {{ background:var(--surface); border-radius:2px; }}
  .carousel::-webkit-scrollbar-thumb {{ background:var(--border); border-radius:2px; }}

  .cs-card {{ flex:0 0 220px; scroll-snap-align:start; background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:14px; position:relative; transition:border .15s; }}
  .cs-card:hover {{ border-color:var(--accent); }}
  .cs-badge {{ display:inline-block; padding:2px 8px; border-radius:4px; font-size:10px; font-weight:700; margin-bottom:8px; }}
  .cs-sched {{ background:var(--accent); color:#0b0f15; }}
  .cs-ft {{ background:var(--surface-2); color:var(--text-muted); }}
  .cs-match {{ display:flex; align-items:center; gap:6px; font-size:14px; font-weight:600; margin-bottom:6px; }}
  .cs-abbr {{ font-weight:700; }}
  .cs-vs {{ color:var(--text-muted); font-size:12px; }}
  .cs-meta {{ font-size:11px; color:var(--text-muted); display:flex; flex-direction:column; gap:2px; margin-bottom:4px; }}
  .cs-date {{ font-size:11px; color:var(--text-muted); }}
  .cs-odds {{ font-size:11px; color:var(--amber); font-family:monospace; margin-top:4px; }}

  /* ─── EMPTY STATE ─── */
  .empty-state {{ text-align:center; padding:60px 20px; color:var(--text-muted); }}

  /* ─── FOOTER ─── */
  footer {{ border-top:1px solid var(--border); padding:20px 0; margin-top:12px; text-align:center; font-size:12px; color:var(--text-muted); }}
  footer a {{ color:var(--accent); text-decoration:none; }}

  @media (max-width:800px) {{ .stats {{ grid-template-columns:repeat(2,1fr); }} .grid {{ grid-template-columns:1fr; }} .hero-match {{ flex-direction:column; gap:16px; }} .hero-team {{ min-width:auto; }} .head-row {{ flex-direction:column; align-items:flex-start; }} .head-info {{ text-align:left; }} .tabs {{ overflow-x:auto; }} .tab {{ padding:10px 14px; white-space:nowrap; }} .hero-content {{ padding:20px 16px; }} .odds-book {{ grid-template-columns:1fr 50px 50px 50px; font-size:12px; }} }}
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
        <div>OSINT Dashboard</div>
        <div style="margin-top:2px">{last_update} · {total_count} articles · {source_count} sources</div>
      </div>
    </div>
  </header>

  <!-- TABS -->
  <div class="tabs" role="tablist">
    <div class="tab active" data-tab="news" onclick="switchTab('news')">World News <span class="tab-badge">{total_count}</span></div>
    <div class="tab" data-tab="football" onclick="switchTab('football')">Football <span class="tab-badge">{fb_count}</span></div>
    <div class="tab tab-more" onclick="void(0)">More ▸</div>
  </div>

  <!-- TAB CONTENT -->
  {news_tab}
  {football_tab}

  <!-- FOOTER -->
  <footer>
    Datagateway — OSINT Aggregator · Daily fetch 07:00 &amp; 18:00 WIB ·
    <a href="https://github.com/jtoemion/Datagateway" target="_blank">github.com/jtoemion/Datagateway</a>
  </footer>
</div>

<script>
// ─── Tab switching ───
function switchTab(name) {{
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.toggle('active', p.id === 'tab-' + name));
}}

// ─── World News filters ───
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
  const tab = document.getElementById('tab-news');
  if (!tab) return;
  const cards = tab.querySelectorAll('.card');
  let visible = 0;
  cards.forEach(c => {{
    const s = c.dataset.source; const ct = c.dataset.cat;
    const ok = (state.source==='all'||s===state.source) && (state.cat==='all'||ct===state.cat);
    const txt = (c.querySelector('.card-title')?.textContent||'').toLowerCase()
              + ' ' + (c.querySelector('.card-excerpt')?.textContent||'').toLowerCase()
              + ' ' + s.toLowerCase();
    const match = !q || txt.includes(q);
    if (ok && match) {{ c.style.display=''; visible++; }} else {{ c.style.display='none'; }}
  }});
  const nr = document.getElementById('noR');
  if (nr) nr.classList.toggle('show', visible===0);
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
    print(f"Datagateway — Build Dashboard v4 ({datetime.now(WIB).strftime('%Y-%m-%d %H:%M WIB')})")
    print("=" * 60)

    total = get_article_count()
    fb = get_football_count()
    articles = get_articles(limit=200)
    print(f"  News: {total} articles, Football: {fb} events")

    html = build_html(articles)

    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
    outpath = DASHBOARD_DIR / "index.html"
    outpath.write_text(html, encoding="utf-8")
    print(f"  Dashboard: {outpath} ({len(html)} bytes)")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
