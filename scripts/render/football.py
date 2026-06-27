"""
Datagateway — Render Football (CODE)
Football tab HTML generation (hero + carousel + football news cards).
"""

from pathlib import Path
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Country code → flag filename mapping for FIFA teams
TEAM_FLAGS: dict[str, str] = {
    "FRA": "fr", "NOR": "no", "IRQ": "iq", "SEN": "sn",
    "ESP": "es", "URU": "uy", "KSA": "sa", "CPV": "cv",
    "AUS": "au", "PAR": "py", "USA": "us", "TUR": "tr",
}


def esc(s) -> str:
    if s is None:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def flag_img(abbr: str) -> str:
    code = TEAM_FLAGS.get(abbr, "").lower()
    if code:
        return f'<img src="assets/flags/{code}.svg" class="flag-icon" alt="{esc(abbr)}" onerror="this.style.display=\'none\'">'
    return ""


def build_football_html(fb_news: list | None = None) -> str:
    """Build Football tab content — hero + carousel + football news section."""
    fb_news = fb_news or []
    events = []
    from scripts.database import get_football_events
    events = get_football_events()

    # Hero: first scheduled match
    hero_candidates = [e for e in events if e.get("event_status") == "STATUS_SCHEDULED"]
    hero = hero_candidates[0] if hero_candidates else (events[0] if events else None)

    hero_html = ""
    if hero:
        hero_html = _hero_card(hero)

    # Carousel
    carousel_html = _carousel(events)

    # Football news section
    news_section = _football_news_section(fb_news)

    return f"""
{hero_html}
<div class="carousel-section">
  <div class="carousel-header">
    <h3>All Matches</h3>
    <span style="font-size:12px;color:var(--text-muted)">{len(events)} matches</span>
  </div>
  <div class="carousel" id="match-carousel">{carousel_html}</div>
</div>

{news_section}
</div>"""


def _hero_card(match: dict) -> str:
    away = esc(match.get("team_away", ""))
    home = esc(match.get("team_home", ""))
    away_abbr = esc(match.get("team_away_abbr", ""))
    home_abbr = esc(match.get("team_home_abbr", ""))
    venue = esc(match.get("venue_name", ""))
    location = esc(match.get("venue_location", ""))
    broadcast = esc(match.get("broadcast", ""))
    attendance = match.get("attendance", "")

    dt = match.get("event_date", "")
    try:
        dt_obj = datetime.fromisoformat(dt.replace("Z", "+00:00")).astimezone(WIB)
        dt_str = dt_obj.strftime("%a, %d %b %H:%M WIB")
    except (ValueError, TypeError):
        dt_str = esc(dt)

    status = match.get("status_detail", "Scheduled")
    if status.lower() == "final" or status.lower() == "ft":
        badge = f'<span class="hero-badge cs-ft">FT</span>'
        score_away = esc(str(match.get("score_away", "0")))
        score_home = esc(str(match.get("score_home", "0")))
    else:
        badge = f'<span class="hero-badge cs-sched">UP NEXT</span>'
        score_away = away_abbr
        score_home = home_abbr

    # Odds
    odds_html = ""
    from scripts.database import get_football_odds
    eid = match["event_id"]
    odds_rows = get_football_odds(eid, market_id=1)
    main_lines = [o for o in odds_rows if o.get("is_main_line") == 1]
    if main_lines:
        aff_groups: dict = {}
        for o in main_lines:
            aff = o.get("affiliate_id")
            if aff not in aff_groups:
                aff_groups[aff] = {"name": o.get("affiliate_name", f"Book {aff}"), "odds": {}}
            ptype = o.get("participant_type", "")
            if "away" in ptype.lower():
                key = "away"
            elif "home" in ptype.lower():
                key = "home"
            else:
                key = "draw"
            aff_groups[aff]["odds"][key] = o.get("price_american", "")

        odds_rows_html = ""
        for aff_id, data in aff_groups.items():
            odd = data["odds"]
            odds_rows_html += (
                f'<div class="odds-row">'
                f'<span class="odds-name">{esc(data["name"])}</span>'
                f'<span class="odds-val">{odd.get("away", "-")}</span>'
                f'<span class="odds-val">{odd.get("draw", "-")}</span>'
                f'<span class="odds-val">{odd.get("home", "-")}</span>'
                f'</div>'
            )
        odds_html = (
            f'<div class="hero-odds-label">Moneyline Odds</div>'
            f'<div class="odds-book">'
            f'<div class="odds-row odds-header">'
            f'<span>Sportsbook</span><span>Away</span><span>Draw</span><span>Home</span>'
            f'</div>'
            f'{odds_rows_html}'
            f'</div>'
        )

    # Attendance display
    att_display = f" \u00b7 {esc(attendance)}" if attendance and attendance != "0" else ""

    return f"""
<div class="hero-card">
  <div class="hero-content">
    <div class="hero-meta-top">
      {badge}
      <span class="hero-season">{esc(match.get("season_type","FIFA World Cup"))}</span>{att_display}
      <span class="hero-date">{dt_str}</span>
    </div>
    <div class="hero-match">
      <div class="hero-team hero-away">
        {flag_img(away_abbr)}
        <span class="ht-abbr">{away_abbr}</span>
        <span class="ht-name">{away}</span>
      </div>
      <div class="hero-score">
        <span class="ht-abbr ht-score">{score_away}</span>
        <span class="ht-vs">vs</span>
        <span class="ht-abbr ht-score">{score_home}</span>
      </div>
      <div class="hero-team hero-home">
        {flag_img(home_abbr)}
        <span class="ht-abbr">{home_abbr}</span>
        <span class="ht-name">{home}</span>
      </div>
    </div>
    <div class="hero-venue">
      <span class="venue-icon">{chr(0x1f4cd)}</span>
      {esc(venue)} \u2014 {esc(location)} \u00b7 <strong>{esc(broadcast)}</strong>
    </div>
    {odds_html}
  </div>
</div>"""


def _carousel(events: list[dict]) -> str:
    cards = ""
    from scripts.database import get_football_odds
    for m in events:
        away_abbr = esc(m.get("team_away_abbr", ""))
        home_abbr = esc(m.get("team_home_abbr", ""))
        away_abbr_raw = m.get("team_away_abbr", "")
        home_abbr_raw = m.get("team_home_abbr", "")
        away = esc(m.get("team_away", ""))
        home = esc(m.get("team_home", ""))
        venue = esc(m.get("venue_name", ""))
        broadcast = esc(m.get("broadcast", ""))

        dt = m.get("event_date", "")
        try:
            dt_obj = datetime.fromisoformat(dt.replace("Z", "+00:00")).astimezone(WIB)
            dt_str = dt_obj.strftime("%a %d %b %H:%M")
        except (ValueError, TypeError):
            dt_str = esc(dt)

        status = m.get("status_detail", "Scheduled")
        is_sched = status.lower() in ("scheduled", "")

        if is_sched:
            badge = f'<span class="cs-badge cs-sched">Scheduled</span>'
            flag_a = flag_img(away_abbr_raw)
            flag_h = flag_img(home_abbr_raw)
            score_line = f'<span class="cs-abbr">{flag_a} {away_abbr}</span><span class="cs-vs">vs</span><span class="cs-abbr">{flag_h} {home_abbr}</span>'
        else:
            badge = f'<span class="cs-badge cs-ft">FT</span>'
            sa = esc(str(m.get("score_away", "0")))
            sh = esc(str(m.get("score_home", "0")))
            score_line = f'<span class="cs-abbr">{away_abbr}</span><span class="cs-vs">{sa}-{sh}</span><span class="cs-abbr">{home_abbr}</span>'

        # Quick odds
        odds_label = ""
        odds_rows = get_football_odds(m["event_id"], market_id=1)
        main_lines = [o for o in odds_rows if o.get("is_main_line") == 1]
        if main_lines:
            prices = sorted(set(str(o.get("price_american", "")) for o in main_lines))
            best = min(prices, key=lambda x: abs(int(x))) if prices else ""
            odds_label = f'<div class="cs-odds">ML: {best}</div>' if best else ''

        cards += (
            f'<div class="cs-card">'
            f'{badge}'
            f'{score_line}'
            f'<div class="cs-info">{esc(venue)}</div>'
            f'<div class="cs-info cs-small">{esc(broadcast)} \u00b7 {dt_str}</div>'
            f'{odds_label}'
            f'</div>'
        )
    return cards


def _football_news_section(fb_news: list) -> str:
    if not fb_news:
        return '<div class="fb-news-section"><div class="fb-news-header"><h3>Latest Football News</h3><span style="font-size:12px;color:var(--text-muted)">0 articles</span></div><p style="color:var(--text-muted);font-size:14px;">No football news available.</p></div>'

    cards = ""
    for a in fb_news:
        title_esc = esc(a.get("title", "?"))
        excerpt_esc = esc((a.get("excerpt") or "")[:200])
        source_name = a.get("source", "")
        article_id = a.get("id", "")
        image_url = a.get("image_url", "")
        date_wib = esc(a.get("date_wib", ""))
        url_esc = esc(a.get("url", ""))
        fg = "#ff6b35"  # default football color
        from scripts.render.news import SOURCE_COLORS
        fg, _ = SOURCE_COLORS.get(source_name, ("#888", "#88888822"))
        from scripts.render.news import source_glyph
        glyph = source_glyph(source_name)

        img_block = ""
        if image_url:
            img_url_esc = esc(image_url)
            img_block = (
                '<div class="card-img fb-img">'
                f'<img src="{img_url_esc}" alt="" loading="lazy" '
                'onerror="this.parentElement.style.display=\'none\'">'
                '</div>'
            )

        cards += (
            f'<article class="card fb-card" data-id="{esc(article_id)}">\n'
            f'  <div class="card-accent" style="background:{fg}"><span>{glyph}</span></div>\n'
            f'  {img_block}\n'
            f'  <div class="card-body">\n'
            f'    <div class="card-meta-top">\n'
            f'      <span class="card-source" style="color:{fg}">{esc(source_name)}</span>\n'
            f'      <span class="card-date">{esc(date_wib)}</span>\n'
            f'    </div>\n'
            f'    <a href="article.html?id={esc(article_id)}" class="card-title">{title_esc}</a>\n'
            f'    <p class="card-excerpt">{excerpt_esc}</p>\n'
            f'  </div>\n'
            f'  <div class="card-footer-actions">\n'
            f'    <div class="card-actions">\n'
            f'      <a href="article.html?id={esc(article_id)}" class="act">\U0001f4d6 Read</a>\n'
            f'      <a href="{url_esc}" target="_blank" rel="noopener" class="act">Original \u2192</a>\n'
            f'    </div>\n'
            f'  </div>\n'
            f'</article>'
        )

    return (
        f'<div class="fb-news-section">\n'
        f'  <div class="fb-news-header">\n'
        f'    <h3>Latest Football News</h3>\n'
        f'    <span style="font-size:12px;color:var(--text-muted)">{len(fb_news)} articles</span>\n'
        f'  </div>\n'
        f'  <div class="grid">\n'
        f'    {cards}\n'
        f'  </div>\n'
        f'</div>'
    )
