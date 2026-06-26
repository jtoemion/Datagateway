#!/usr/bin/env python3
"""
Datagateway — Dashboard Builder
Baca semua file .md di news/, generate HTML dashboard/index.html.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

WIB = timezone(timedelta(hours=7))
REPO_ROOT = Path(__file__).resolve().parent.parent
NEWS_DIR = REPO_ROOT / "news"
DASHBOARD_DIR = REPO_ROOT / "dashboard"
ARTICLES_PER_PAGE = 48


def parse_md_article(filepath: Path) -> dict | None:
    """Parse frontmatter + excerpt dari file .md berita."""
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception:
        return None

    # Parse YAML-like frontmatter (simple, no deps)
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

    # Ambil excerpt: first paragraph setelah judul
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
            # Bersihin bold/markdown
            excerpt = re.sub(r'\*\*(.*?)\*\*', r'\1', excerpt)
            excerpt = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', excerpt)
            break

    if not excerpt:
        excerpt = body[:200].replace("\n", " ").strip()

    return {
        "id": frontmatter.get("id", ""),
        "source": frontmatter.get("source", ""),
        "title": frontmatter.get("title", ""),
        "url": frontmatter.get("url", ""),
        "date": frontmatter.get("date", ""),
        "date_wib": frontmatter.get("date_wib", ""),
        "category": frontmatter.get("category", ""),
        "lang": frontmatter.get("lang", ""),
        "excerpt": excerpt[:300],
        "filename": filepath.name,
        "relpath": str(filepath.relative_to(REPO_ROOT)),
    }


def collect_articles() -> list[dict]:
    """Kumpulin semua artikel dari news/."""
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


def build_html(articles: list[dict]) -> str:
    """Generate dashboard HTML."""
    sources = sorted(set(a["source"] for a in articles if a["source"]))
    categories = sorted(set(a["category"] for a in articles if a["category"]))

    # Stats
    today = datetime.now(WIB).strftime("%Y-%m-%d")
    today_count = sum(1 for a in articles if a["date"].startswith(today))
    source_count = len(sources)
    total_count = len(articles)

    # Latest update time
    last_update = datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB")

    # Cards HTML
    cards_html = ""
    for a in articles[:ARTICLES_PER_PAGE]:
        source_badge = f"""<span class="badge badge-{a['lang']}">{a['source']}</span>"""
        cat_badge = f"""<span class="badge badge-cat">{a['category']}</span>"""
        cards_html += f"""
        <a href="{a['url']}" target="_blank" rel="noopener" class="article-card">
            <div class="card-header">
                {source_badge} {cat_badge}
                <span class="card-date">{a['date_wib'] or a['date'][:10]}</span>
            </div>
            <h3 class="card-title">{a['title']}</h3>
            <p class="card-excerpt">{a['excerpt']}</p>
            <div class="card-footer">
                <span class="card-read">Baca →</span>
            </div>
        </a>"""

    # Source filter buttons
    source_btns = ""
    for s in sources:
        count = sum(1 for a in articles if a["source"] == s)
        source_btns += f"""<button class="filter-btn" data-filter="source:{s}">{s} ({count})</button>\n            """

    # Category filter
    cat_btns = ""
    for c in categories:
        count = sum(1 for a in articles if a["category"] == c)
        cat_btns += f"""<button class="filter-btn" data-filter="category:{c}">{c.title()} ({count})</button>\n            """

    latest_date = articles[0]["date"][:10] if articles else "—"

    html = f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Datagateway — OSINT News Dashboard</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  :root {{
    --bg: #0d1117;
    --surface: #161b22;
    --surface-2: #21262d;
    --border: #30363d;
    --text: #e6edf3;
    --text-muted: #8b949e;
    --accent: #58a6ff;
    --accent-green: #3fb950;
    --accent-yellow: #d29922;
    --radius: 8px;
  }}

  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    min-height: 100vh;
  }}

  .container {{ max-width: 1280px; margin: 0 auto; padding: 0 24px; }}

  /* HEADER */
  header {{
    border-bottom: 1px solid var(--border);
    padding: 24px 0 16px;
    margin-bottom: 24px;
  }}

  header h1 {{
    font-size: 28px;
    font-weight: 700;
    letter-spacing: -0.5px;
    display: flex;
    align-items: center;
    gap: 12px;
  }}

  header h1 span {{
    background: linear-gradient(135deg, var(--accent), var(--accent-green));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }}

  .subtitle {{
    color: var(--text-muted);
    font-size: 14px;
    margin-top: 4px;
    display: flex;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 8px;
  }}

  /* STATS */
  .stats {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 12px;
    margin-bottom: 24px;
  }}

  .stat-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px;
    text-align: center;
  }}

  .stat-card .num {{
    font-size: 32px;
    font-weight: 700;
    color: var(--accent);
  }}

  .stat-card .label {{
    font-size: 12px;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}

  /* FILTERS */
  .filters {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 24px;
    padding: 16px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
  }}

  .filter-btn {{
    background: var(--surface-2);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 6px 14px;
    font-size: 12px;
    cursor: pointer;
    transition: all 0.2s;
    white-space: nowrap;
  }}

  .filter-btn:hover {{
    background: var(--accent);
    color: #fff;
    border-color: var(--accent);
  }}

  .filter-btn.active {{
    background: var(--accent);
    color: #fff;
    border-color: var(--accent);
  }}

  .filter-btn.clear-btn {{
    background: transparent;
    color: var(--text-muted);
    border: 1px dashed var(--border);
  }}

  .filter-btn.clear-btn:hover {{
    border-color: var(--accent-yellow);
    color: var(--accent-yellow);
    background: transparent;
  }}

  /* SEARCH */
  .search-bar {{
    margin-bottom: 24px;
  }}

  .search-bar input {{
    width: 100%;
    padding: 10px 16px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    color: var(--text);
    font-size: 14px;
    outline: none;
    transition: border 0.2s;
  }}

  .search-bar input:focus {{
    border-color: var(--accent);
  }}

  .search-bar input::placeholder {{
    color: var(--text-muted);
  }}

  /* ARTICLE GRID */
  .article-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 16px;
    margin-bottom: 32px;
  }}

  .article-card {{
    display: flex;
    flex-direction: column;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px;
    text-decoration: none;
    color: inherit;
    transition: all 0.2s;
  }}

  .article-card:hover {{
    border-color: var(--accent);
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(88, 166, 255, 0.15);
  }}

  .card-header {{
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
    flex-wrap: wrap;
  }}

  .badge {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.3px;
  }}

  .badge-id {{ background: #1f6feb33; color: #58a6ff; }}
  .badge-en {{ background: #3fb95033; color: #3fb950; }}
  .badge-cat {{ background: #d2992233; color: #d29922; font-size: 10px; }}

  .card-date {{
    margin-left: auto;
    font-size: 11px;
    color: var(--text-muted);
    white-space: nowrap;
  }}

  .card-title {{
    font-size: 15px;
    font-weight: 600;
    line-height: 1.4;
    margin-bottom: 8px;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }}

  .card-excerpt {{
    font-size: 13px;
    color: var(--text-muted);
    line-height: 1.5;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
    flex: 1;
  }}

  .card-footer {{
    margin-top: 12px;
    padding-top: 8px;
    border-top: 1px solid var(--border);
  }}

  .card-read {{
    font-size: 12px;
    color: var(--accent);
    font-weight: 500;
  }}

  /* NO RESULTS */
  .no-results {{
    text-align: center;
    padding: 48px 24px;
    color: var(--text-muted);
    grid-column: 1 / -1;
  }}

  /* FOOTER */
  footer {{
    border-top: 1px solid var(--border);
    padding: 24px 0;
    margin-top: 24px;
    text-align: center;
    font-size: 12px;
    color: var(--text-muted);
  }}

  /* RESPONSIVE */
  @media (max-width: 768px) {{
    .article-grid {{ grid-template-columns: 1fr; }}
    .stats {{ grid-template-columns: repeat(2, 1fr); }}
    header h1 {{ font-size: 22px; }}
  }}

  @media (max-width: 480px) {{
    .filters {{ flex-direction: column; }}
    .stats {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>◈ <span>Datagateway</span></h1>
    <div class="subtitle">
      <span>OSINT News Dashboard</span>
      <span>Last update: {last_update} · {total_count} articles from {source_count} sources</span>
    </div>
  </header>

  <div class="stats">
    <div class="stat-card">
      <div class="num">{today_count}</div>
      <div class="label">Today</div>
    </div>
    <div class="stat-card">
      <div class="num">{total_count}</div>
      <div class="label">Total Articles</div>
    </div>
    <div class="stat-card">
      <div class="num">{source_count}</div>
      <div class="label">Sources</div>
    </div>
    <div class="stat-card">
      <div class="num">{latest_date}</div>
      <div class="label">Latest</div>
    </div>
  </div>

  <div class="search-bar">
    <input type="text" id="searchInput" placeholder="Cari berita..." oninput="filterArticles()">
  </div>

  <div class="filters" id="filters">
    <button class="filter-btn clear-btn active" data-filter="all" onclick="setFilter('all')">All ({len(articles)})</button>
    {source_btns}
  </div>

  <div class="filters" id="catFilters">
    <button class="filter-btn clear-btn active" data-filter="cat:all" onclick="setCategory('all')">All Categories</button>
    {cat_btns}
  </div>

  <div class="article-grid" id="articleGrid">
    {cards_html}
  </div>

  <div class="no-results" id="noResults" style="display:none">
    Tidak ada berita yang cocok dengan filter yang dipilih.
  </div>

  <footer>
    Datagateway — OSINT News Aggregator · Data dari portal berita terbuka · Updates: pagi & sore
  </footer>
</div>

<script>
let activeFilter = 'all';
let activeCategory = 'cat:all';

function filterArticles() {{
  const search = document.getElementById('searchInput').value.toLowerCase();
  const grid = document.getElementById('articleGrid');
  const cards = grid.querySelectorAll('.article-card');
  let visible = 0;

  cards.forEach(card => {{
    const source = card.querySelector('.badge:first-child')?.textContent?.trim()?.toLowerCase() || '';
    const catEl = card.querySelector('.badge-cat');
    const category = catEl?.textContent?.trim()?.toLowerCase() || '';
    const title = card.querySelector('.card-title')?.textContent?.toLowerCase() || '';
    const excerpt = card.querySelector('.card-excerpt')?.textContent?.toLowerCase() || '';

    const matchSource = activeFilter === 'all' || source.includes(activeFilter.replace('source:', ''));
    const matchCat = activeCategory === 'cat:all' || category.includes(activeCategory.replace('category:', ''));
    const matchSearch = !search || title.includes(search) || excerpt.includes(search);

    if (matchSource && matchCat && matchSearch) {{
      card.style.display = '';
      visible++;
    }} else {{
      card.style.display = 'none';
    }}
  }});

  document.getElementById('noResults').style.display = visible === 0 ? '' : 'none';
}}

function setFilter(filter) {{
  activeFilter = filter;
  document.querySelectorAll('#filters .filter-btn').forEach(btn => {{
    const val = btn.dataset.filter || 'all';
    btn.classList.toggle('active', val === filter || (filter === 'all' && val === 'all'));
  }});
  filterArticles();
}}

function setCategory(cat) {{
  activeCategory = cat;
  document.querySelectorAll('#catFilters .filter-btn').forEach(btn => {{
    const val = btn.dataset.filter || 'cat:all';
    btn.classList.toggle('active', val === cat || (cat === 'cat:all' && val === 'cat:all'));
  }});
  filterArticles();
}}
</script>
</body>
</html>"""

    return html


def main():
    print(f"Datagateway — Build Dashboard ({datetime.now(WIB).strftime('%Y-%m-%d %H:%M WIB')})")
    print("=" * 60)

    articles = collect_articles()
    print(f"  Collected: {len(articles)} articles")

    html = build_html(articles)

    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
    outpath = DASHBOARD_DIR / "index.html"
    outpath.write_text(html, encoding="utf-8")
    print(f"  Dashboard: {outpath} ({len(html)} bytes)")

    print(f"\n{'=' * 60}")
    print(f"Selesai. Dashboard → dashboard/index.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
