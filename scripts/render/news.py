"""
Datagateway — Render News (CODE)
Feed cards and World News tab HTML generation.
"""

from pathlib import Path
from datetime import datetime, timezone, timedelta

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
WIB = timezone(timedelta(hours=7))

SOURCE_COLORS: dict[str, tuple[str, str]] = {
    "CNN Indonesia": ("#e31e24", "#e31e2433"),
    "Detik": ("#ffffff", "#ffffff22"),
    "CNBC Indonesia": ("#0055a5", "#0055a533"),
    "Antara": ("#1b5e20", "#1b5e2033"),
    "Republika": ("#172554", "#17255433"),
    "BBC Indonesia": ("#ff6b35", "#ff6b3533"),
    "BBC News": ("#111111", "#11111133"),
    "BBC Football": ("#ff6b35", "#ff6b3533"),
    "Sky Sports Football": ("#00b050", "#00b05033"),
    "The Guardian Football": ("#052962", "#05296233"),
    "Fox Sports Soccer": ("#e31e24", "#e31e2433"),
}

SOURCE_GLYPH: dict[str, str] = {
    "CNN Indonesia": "C",
    "Detik": "D",
    "CNBC Indonesia": "B",
    "Antara": "A",
    "Republika": "R",
    "BBC Indonesia": "B",
    "BBC News": "B",
    "BBC Football": "B",
    "Sky Sports Football": "S",
    "The Guardian Football": "G",
    "Fox Sports Soccer": "F",
}


def esc(s) -> str:
    if s is None:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;")


def source_glyph(source: str) -> str:
    glyph = SOURCE_GLYPH.get(source)
    return glyph if glyph else (source[0].upper() if source else "?")


def card_html(article: dict) -> str:
    title_esc = esc(article.get("title", "?"))
    excerpt_esc = esc((article.get("excerpt") or "")[:350])
    url_esc = esc(article.get("url", ""))
    wikilink_esc = esc(article.get("wikilink", ""))
    image_url = article.get("image_url", "")
    source_name = article.get("source", "")
    cat = article.get("category", "umum")
    lang = article.get("lang", "id")
    article_id = article.get("id", "")
    date_wib = esc(article.get("date_wib", ""))
    glyph = source_glyph(source_name)
    fg, bg = SOURCE_COLORS.get(source_name, ("#888", "#88888822"))

    # Build image block only if image_url exists
    img_block = ""
    if image_url:
        img_url_esc = esc(image_url)
        img_block = (
            '<div class="card-img">'
            f'<img src="{img_url_esc}" alt="" loading="lazy" '
            'onerror="this.parentElement.style.display=\'none\'">'
            '</div>'
        )

    # Reading time
    body_words = len(excerpt_esc.split())
    reading_time = max(1, body_words // 200) if body_words > 0 else ""

    return (
        f'<article class="card" data-id="{esc(article_id)}">\n'
        f'  <div class="card-accent" style="background:{fg}"><span>{glyph}</span></div>\n'
        f'  {img_block}\n'
        f'  <div class="card-body">\n'
        f'    <div class="card-meta-top">\n'
        f'      <span class="card-source" style="color:{fg}">{esc(source_name)}</span>\n'
        f'      <span class="card-lang">{esc(lang).upper()}</span>\n'
        f'      <span class="card-date">{esc(date_wib)}</span>\n'
        + (f'      <span class="card-readtime">\u23f1{reading_time}m</span>\n' if reading_time else '')
        + f'    </div>\n'
        f'    <a href="article.html?id={esc(article_id)}" class="card-title">{title_esc}</a>\n'
        f'    <p class="card-excerpt">{excerpt_esc}</p>\n'
        f'    <div class="card-meta">\n'
        f'      <span class="card-cat">{esc(cat)}</span>\n'
        f'      <span class="card-id" style="font-family:mono;font-size:9px;color:var(--text-muted)">{esc(article_id[:12])}</span>\n'
        f'    </div>\n'
        f'  </div>\n'
        f'  <div class="card-footer-actions">\n'
        f'    <div class="wiki-wrapper">\n'
        f'      <span class="wiki-label">WIKILINK</span>\n'
        f'      <code class="wiki-link" data-wiki="{esc(wikilink_esc or "untagged")}">{esc(wikilink_esc[:30] or "untagged")}</code>\n'
        f'      <button class="act wiki-copy" '
        'onclick="navigator.clipboard.writeText(this.previousElementSibling.textContent.trim());'
        'this.classList.add(\'copied\');setTimeout(()=>this.classList.remove(\'copied\'),800)">COPY</button>\n'
        f'    </div>\n'
        f'    <div class="card-actions">\n'
        f'      <a href="article.html?id={esc(article_id)}" class="act">\U0001f4d6 Read</a>\n'
        f'      <a href="{url_esc}" target="_blank" rel="noopener" class="act">Original \u2192</a>\n'
        f'    </div>\n'
        f'  </div>\n'
        f'</article>'
    )


def build_world_news_html(articles: list[dict]) -> str:
    """Build World News tab content."""
    world_articles = [a for a in articles if a.get("category") != "football"]
    today = datetime.now(WIB).strftime("%Y-%m-%d")
    today_count = sum(1 for a in world_articles if (a.get("date") or "").startswith(today))
    total_count = len(world_articles)

    src_counts: dict[str, int] = {}
    cat_counts: dict[str, int] = {}
    for a in world_articles:
        src = a.get("source", "?")
        src_counts[src] = src_counts.get(src, 0) + 1
        cat = a.get("category", "umum")
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

    latest_date = world_articles[0]["date"][:10] if world_articles else "\u2014"

    stats = (
        f'    <div class="stat-card"><div class="num">{today_count}</div><div class="stat-label">Today</div></div>\n'
        f'    <div class="stat-card"><div class="num">{total_count}</div><div class="stat-label">Total</div></div>\n'
        f'    <div class="stat-card"><div class="num">{len(src_counts)}</div><div class="stat-label">Sources</div></div>\n'
        f'    <div class="stat-card"><div class="num">{latest_date}</div><div class="stat-label">Latest</div></div>'
    )

    src_btns = '<button class="flt flt-src active" data-filter="all">All</button>'
    for s, cnt in sorted(src_counts.items()):
        fg, _ = SOURCE_COLORS.get(s, ("#888", "#88888822"))
        src_btns += f'<button class="flt flt-src" data-filter="{esc(s)}" style="--flt-clr:{fg}">{esc(s)} <small>{cnt}</small></button>'

    cat_btns = '<button class="flt flt-cat active" data-filter="all">All</button>'
    for c, cnt in sorted(cat_counts.items()):
        cat_btns += f'<button class="flt flt-cat" data-filter="{esc(c)}">{esc(c)} <small>{cnt}</small></button>'

    cards = "\n".join(card_html(a) for a in world_articles)

    return (
        f'\n    <div class="stats">{stats}</div>\n'
        f'\n    <div class="toolbar">\n'
        f'      <input type="text" class="srch" id="search" placeholder="Search titles, sources, excerpts..." oninput="applyFilters()" />\n'
        f'      <div class="flt-group"><span class="flt-glabel">SOURCE</span><div class="flt-row" id="src-filters">{src_btns}</div></div>\n'
        f'      <div class="flt-group"><span class="flt-glabel">CATEGORY</span><div class="flt-row" id="cat-filters">{cat_btns}</div></div>\n'
        f'    </div>\n'
        f'\n    <div class="grid" id="news-grid">{cards}</div>'
    )
