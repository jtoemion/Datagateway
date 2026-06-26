#!/usr/bin/env python3
"""
Datagateway — Article Viewer Builder
Generates dashboard/article.html with embedded article data and vis.js graph.
"""

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
import hashlib

from scripts.database import (
    init_db,
    get_articles,
    get_scraped_article,
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
    "NY Times": ("#333333", "#33333333"),
}
DEFAULT_COLOR = ("#58a6ff", "#58a6ff33")


def esc(text: str) -> str:
    """Escape HTML entities."""
    if not isinstance(text, str):
        text = str(text or "")
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def format_date(dt_str: str) -> str:
    """Format date for display."""
    if not dt_str:
        return ""
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.astimezone(WIB).strftime("%a, %d %b %Y · %H:%M WIB")
    except Exception:
        return dt_str[:16]


def build_graph_data(articles: list[dict], current_id: str) -> dict:
    """Build vis.js nodes and edges for the graph."""
    nodes = []
    edges = []
    current_idx = None

    # Index articles by id
    id_to_idx = {a["id"]: i for i, a in enumerate(articles)}

    # Current article info
    current_article = next((a for a in articles if a["id"] == current_id), None)

    # Create nodes
    for i, a in enumerate(articles):
        is_current = a["id"] == current_id
        is_connected = False

        if current_article:
            # Check connection criteria
            same_source = a["source"] == current_article["source"]
            same_cat = a.get("category") == current_article.get("category")
            same_date = (a.get("date", "")[:10] == current_article.get("date", "")[:10]) if a.get("date") and current_article.get("date") else False
            is_connected = same_source or same_cat or same_date

        src = a.get("source", "")
        fg, bg = SOURCE_COLORS.get(src, DEFAULT_COLOR)

        if is_current:
            size = 30
            border_width = 4
            color = {"background": "#1e3a5f", "border": "#60a5fa", "highlight": {"background": "#1e3a5f", "border": "#60a5fa"}}
            font = {"color": "#ffffff", "size": 14, "face": "system-ui", "strokeWidth": 2, "strokeColor": "#60a5fa"}
            title = f"<b style='color:#60a5fa'>{esc(a.get('title', ''))}</b><br><span style='color:#888'>◈ Current Article</span>"
        elif is_connected:
            size = 20
            border_width = 2
            color = {"background": bg, "border": fg, "highlight": {"background": bg, "border": fg}}
            font = {"color": "#e2e8f0", "size": 12, "face": "system-ui"}
            title = esc(a.get("title", ""))
        else:
            size = 12
            border_width = 1
            color = {"background": "#1c2533", "border": "#253040", "highlight": {"background": "#253040", "border": "#60a5fa"}}
            font = {"color": "#8395a8", "size": 10, "face": "system-ui"}
            title = esc(a.get("title", ""))

        nodes.append({
            "id": i,
            "label": a.get("title", "")[:40] + ("..." if len(a.get("title", "")) > 40 else ""),
            "title": title,
            "size": size,
            "borderWidth": border_width,
            "color": color,
            "font": font,
            "article_id": a["id"],
            "is_current": is_current,
            "is_connected": is_connected,
        })

        if is_current:
            current_idx = i

    # Create edges
    if current_article and current_idx is not None:
        for i, a in enumerate(articles):
            if i == current_idx:
                continue
            same_source = a["source"] == current_article["source"]
            same_cat = a.get("category") == current_article.get("category")
            same_date = (a.get("date", "")[:10] == current_article.get("date", "")[:10]) if a.get("date") and current_article.get("date") else False

            if same_source:
                edges.append({"from": current_idx, "to": i, "color": {"color": "#60a5fa", "opacity": 0.4}, "width": 1})
            if same_cat and not same_source:
                edges.append({"from": current_idx, "to": i, "color": {"color": "#4ade80", "opacity": 0.3}, "width": 1})
            if same_date and not same_source and not same_cat:
                edges.append({"from": current_idx, "to": i, "color": {"color": "#fbbf24", "opacity": 0.3}, "width": 1})

    return {"nodes": nodes, "edges": edges}


def build_html(articles: list[dict], current_id: str) -> str:
    """Build the complete article viewer HTML."""
    current_article = next((a for a in articles if a["id"] == current_id), None)
    if not current_article:
        return "<html><body><h1>Article not found</h1></body></html>"

    # Get scraped content
    scraped = get_scraped_article(current_id)
    full_html = scraped.get("full_html", "") if scraped else ""
    author = scraped.get("author", "") if scraped else ""
    images_json = scraped.get("images_json", "[]") if scraped else "[]"
    try:
        images = json.loads(images_json)
    except:
        images = []

    src = current_article.get("source", "")
    fg, bg = SOURCE_COLORS.get(src, DEFAULT_COLOR)
    date_display = format_date(current_article.get("date", ""))
    category = current_article.get("category", "umum").title()

    # Related articles (same source or category)
    related = [
        a for a in articles
        if a["id"] != current_id
        and (a["source"] == src or a.get("category") == current_article.get("category"))
    ][:8]

    # Graph data
    graph = build_graph_data(articles, current_id)
    graph_json = json.dumps(graph, ensure_ascii=False)

    # All articles for JSON embedding
    all_articles_json = json.dumps([
        {
            "id": a["id"],
            "title": a.get("title", ""),
            "source": a.get("source", ""),
            "category": a.get("category", ""),
            "date": a.get("date", ""),
            "wikilink": a.get("wikilink", ""),
            "url": a.get("url", ""),
        }
        for a in articles
    ], ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(current_article.get('title', 'Article'))} — Datagateway</title>
<link rel="stylesheet" href="https://unpkg.com/vis-network/styles/vis-network.min.css">
<style>
  *,*::before,*::after {{ box-sizing:border-box; margin:0; padding:0; }}
  :root {{
    --bg:#1e1e1e; --surface:#252526; --surface-2:#2d2d30;
    --border:#3e3e42; --text:#d4d4d4; --text-muted:#858585;
    --accent:#60a5fa; --green:#4ade80; --amber:#fbbf24;
    --radius:8px; --font:'Georgia','Noto Serif',serif;
    --ui:'system-ui','Segoe UI',Roboto,Helvetica,Arial,sans-serif;
  }}
  html {{ font-size:15px; }}
  body {{
    font-family:var(--font); background:var(--bg); color:var(--text);
    line-height:1.7; min-height:100vh;
  }}

  /* ─── TOP BAR ─── */
  .topbar {{
    display:flex; align-items:center; justify-content:space-between;
    padding:0 20px; height:48px; background:var(--surface);
    border-bottom:1px solid var(--border); position:sticky; top:0; z-index:100;
  }}
  .topbar-logo {{
    display:flex; align-items:center; gap:10px;
    text-decoration:none; color:var(--text);
  }}
  .topbar-logo .icon {{
    width:28px; height:28px; border-radius:6px;
    background:linear-gradient(135deg,#60a5fa,#4ade80);
    display:flex; align-items:center; justify-content:center;
    font-size:14px; font-weight:700; color:#1e1e1e;
  }}
  .topbar-logo span {{
    font-family:var(--ui); font-size:15px; font-weight:600;
    background:linear-gradient(135deg,#60a5fa,#4ade80);
    -webkit-background-clip:text; -webkit-text-fill-color:transparent;
  }}
  .topbar-back {{
    font-family:var(--ui); font-size:13px; color:var(--text-muted);
    text-decoration:none; display:flex; align-items:center; gap:6px;
    transition:color .15s;
  }}
  .topbar-back:hover {{ color:var(--accent); }}

  /* ─── LAYOUT ─── */
  .layout {{
    display:grid; grid-template-columns:3fr 2fr;
    min-height:calc(100vh - 48px);
  }}
  @media (max-width:900px) {{
    .layout {{ grid-template-columns:1fr; }}
  }}

  /* ─── LEFT PANEL (ARTICLE) ─── */
  .article-panel {{
    padding:40px 20px 60px;
    border-right:1px solid var(--border);
    overflow-y:auto;
  }}
  .article-inner {{
    max-width:720px; margin:0 auto;
  }}

  /* Article header */
  .article-header {{
    margin-bottom:28px;
  }}
  .article-badges {{
    display:flex; align-items:center; gap:10px; margin-bottom:14px; flex-wrap:wrap;
  }}
  .source-badge {{
    display:inline-flex; align-items:center; gap:5px;
    padding:4px 12px; border-radius:20px; font-family:var(--ui);
    font-size:11px; font-weight:700; letter-spacing:0.3px;
    background:{{bg}}; color:{{fg}}; border:1px solid {{fg}};
  }}
  .category-badge {{
    display:inline-block; padding:3px 10px; border-radius:4px;
    font-family:var(--ui); font-size:10px; font-weight:600;
    text-transform:uppercase; letter-spacing:0.5px;
    background:#d2992233; color:#d29922;
  }}
  .lang-badge {{
    font-family:var(--ui); font-size:10px; font-weight:700;
    text-transform:uppercase; padding:2px 7px; border-radius:3px;
    background:#1f6feb33; color:#60a5fa;
  }}
  .article-date {{
    font-family:var(--ui); font-size:12px; color:var(--text-muted);
    margin-bottom:8px;
  }}
  .article-title {{
    font-family:var(--font); font-size:32px; font-weight:700;
    line-height:1.25; color:#ffffff; margin-bottom:8px;
    letter-spacing:-0.5px;
  }}
  .article-author {{
    font-family:var(--ui); font-size:13px; color:var(--text-muted);
    font-style:italic;
  }}

  /* Article body */
  .article-body {{
    font-size:17px; line-height:1.8;
  }}
  .article-body p {{ margin-bottom:1.4em; }}
  .article-body h1,.article-body h2,.article-body h3 {{
    color:#ffffff; font-weight:700; line-height:1.3;
    margin:1.8em 0 0.8em;
  }}
  .article-body h1 {{ font-size:26px; }}
  .article-body h2 {{ font-size:22px; }}
  .article-body h3 {{ font-size:18px; }}
  .article-body a {{ color:var(--accent); text-decoration:none; }}
  .article-body a:hover {{ text-decoration:underline; }}
  .article-body img {{
    max-width:100%; border-radius:var(--radius); margin:1.5em auto;
    display:block; box-shadow:0 4px 20px rgba(0,0,0,.4);
  }}
  .article-body blockquote {{
    border-left:3px solid var(--accent); padding:4px 0 4px 20px;
    margin:1.5em 0; color:var(--text-muted); font-style:italic;
  }}
  .article-body pre {{
    background:#111111; border:1px solid var(--border);
    border-radius:var(--radius); padding:16px; overflow-x:auto;
    font-family:'Consolas','Monaco',monospace; font-size:13px;
    line-height:1.5; margin:1.5em 0;
  }}
  .article-body code {{
    font-family:'Consolas','Monaco',monospace; font-size:0.9em;
    background:#111111; padding:2px 6px; border-radius:4px;
  }}
  .article-body pre code {{ background:transparent; padding:0; }}
  .article-body ul,.article-body ol {{
    padding-left:24px; margin-bottom:1.4em;
  }}
  .article-body li {{ margin-bottom:0.4em; }}
  .article-body figure {{ margin:1.5em 0; text-align:center; }}
  .article-body figcaption {{
    font-size:13px; color:var(--text-muted); margin-top:8px;
    font-style:italic;
  }}
  .article-body strong {{ color:#ffffff; font-weight:600; }}
  .article-body em {{ color:var(--text-muted); }}

  /* Empty content */
  .article-empty {{
    padding:40px 20px; text-align:center; color:var(--text-muted);
    font-family:var(--ui);
  }}

  /* Wikilinks section */
  .wikilinks-section {{
    margin-top:48px; padding-top:24px;
    border-top:1px solid var(--border);
  }}
  .wikilinks-title {{
    font-family:var(--ui); font-size:12px; text-transform:uppercase;
    letter-spacing:0.5px; color:var(--text-muted); margin-bottom:14px;
    font-weight:600;
  }}
  .wikilinks-grid {{
    display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:10px;
  }}
  .wikilink-card {{
    display:flex; align-items:center; gap:8px;
    padding:10px 14px; background:var(--surface-2);
    border:1px solid var(--border); border-radius:var(--radius);
    text-decoration:none; color:var(--text); font-family:var(--ui);
    font-size:13px; transition:all .15s;
  }}
  .wikilink-card:hover {{
    border-color:var(--accent); background:var(--surface);
  }}
  .wikilink-source {{
    width:8px; height:8px; border-radius:50%; flex-shrink:0;
  }}
  .wikilink-text {{ flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
  .wikilink-arrow {{ color:var(--text-muted); font-size:11px; flex-shrink:0; }}

  /* ─── RIGHT PANEL (GRAPH) ─── */
  .graph-panel {{
    background:var(--surface); position:sticky; top:48px;
    height:calc(100vh - 48px); display:flex; flex-direction:column;
  }}
  .graph-header {{
    padding:16px 20px; border-bottom:1px solid var(--border);
    display:flex; align-items:center; justify-content:space-between;
  }}
  .graph-title {{
    font-family:var(--ui); font-size:13px; font-weight:600;
    color:var(--text);
  }}
  .graph-subtitle {{
    font-family:var(--ui); font-size:11px; color:var(--text-muted);
    margin-top:2px;
  }}
  .graph-legend {{
    display:flex; gap:12px; align-items:center;
  }}
  .legend-item {{
    display:flex; align-items:center; gap:5px;
    font-family:var(--ui); font-size:10px; color:var(--text-muted);
  }}
  .legend-dot {{
    width:8px; height:8px; border-radius:50%;
  }}
  #graph-container {{
    flex:1; overflow:hidden;
  }}
  .graph-footer {{
    padding:12px 20px; border-top:1px solid var(--border);
    font-family:var(--ui); font-size:11px; color:var(--text-muted);
    text-align:center;
  }}
  .graph-footer span {{ color:var(--accent); }}

  @media (max-width:900px) {{
    .graph-panel {{ position:relative; top:0; height:400px; border-top:1px solid var(--border); }}
    .article-panel {{ border-right:none; }}
  }}
</style>
</head>
<body>

<!-- TOP BAR -->
<div class="topbar">
  <a href="index.html" class="topbar-logo">
    <div class="icon">◈</div>
    <span>Datagateway</span>
  </a>
  <a href="index.html" class="topbar-back">← Back to Dashboard</a>
</div>

<!-- MAIN LAYOUT -->
<div class="layout">

  <!-- LEFT: ARTICLE CONTENT -->
  <div class="article-panel">
    <div class="article-inner">

      <div class="article-header">
        <div class="article-badges">
          <span class="source-badge">{esc(src)}</span>
          <span class="category-badge">{category}</span>
          <span class="lang-badge">{current_article.get('lang','id')}</span>
        </div>
        <div class="article-date">{date_display}</div>
        <h1 class="article-title">{esc(current_article.get('title',''))}</h1>
        {f'<div class="article-author">By {esc(author)}</div>' if author else ''}
      </div>

      <div class="article-body">
        {full_html if full_html else f'<div class="article-empty"><p>Full article content not yet scraped.</p><p style="margin-top:12px;font-size:14px;"><a href="{esc(current_article.get("url",""))}" target="_blank" style="color:var(--accent)">Read original article →</a></p></div>'}
      </div>

      <!-- RELATED ARTICLES (WIKILINKS) -->
      {build_wikilinks_section(related, articles) if related else ''}

    </div>
  </div>

  <!-- RIGHT: GRAPH -->
  <div class="graph-panel">
    <div class="graph-header">
      <div>
        <div class="graph-title">Article Graph</div>
        <div class="graph-subtitle">Connections by source · category · date</div>
      </div>
      <div class="graph-legend">
        <div class="legend-item"><div class="legend-dot" style="background:#60a5fa"></div> current</div>
        <div class="legend-item"><div class="legend-dot" style="background:#4ade80"></div> same category</div>
        <div class="legend-item"><div class="legend-dot" style="background:#fbbf24"></div> same date</div>
      </div>
    </div>
    <div id="graph-container"></div>
    <div class="graph-footer">
      <span>{len(related)}</span> related articles · click node to navigate
    </div>
  </div>

</div>

<!-- EMBEDDED DATA -->
<script id="graph-data" type="application/json">{graph_json}</script>
<script id="articles-data" type="application/json">{all_articles_json}</script>

<!-- VIS.JS -->
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>

<script>
// ─── Parse URL params ───
function getArticleId() {{
  const params = new URLSearchParams(window.location.search);
  return params.get('id') || '';
}}

// ─── Graph setup ───
function initGraph() {{
  const dataEl = document.getElementById('graph-data');
  if (!dataEl) return;
  const graphData = JSON.parse(dataEl.textContent || '{{}}');
  const nodes = new vis.DataSet(graphData.nodes || []);
  const edges = new vis.DataSet(graphData.edges || []);

  const container = document.getElementById('graph-container');
  if (!container) return;

  const options = {{
    nodes: {{
      shape: 'dot',
      shadow: {{ enabled: true, size: 15, x: 0, y: 3 }},
      scaling: {{ min: 8, max: 35 }},
    }},
    edges: {{
      smooth: {{ type: 'continuous', roundness: 0.5 }},
      width: 1.5,
    }},
    physics: {{
      forceAtlas2Based: {{
        gravitationalConstant: -80,
        centralGravity: 0.01,
        springLength: 120,
        springConstant: 0.08,
        damping: 0.4,
        avoidOverlap: 0.5,
      }},
      maxVelocity: 50,
      solver: 'forceAtlas2Based',
      timestep: 0.35,
      stabilization: {{ iterations: 150 }},
    }},
    interaction: {{
      hover: true,
      tooltipDelay: 100,
      zoomView: true,
      dragView: true,
    }},
    layout: {{
      improvedLayout: true,
    }},
  }};

  const network = new vis.Network(container, {{ nodes, edges }}, options);

  // Click to navigate
  network.on('click', function(params) {{
    if (params.nodes.length > 0) {{
      const nodeId = params.nodes[0];
      const node = nodes.get(nodeId);
      if (node && node.article_id) {{
        window.location.href = 'article.html?id=' + encodeURIComponent(node.article_id);
      }}
    }}
  }});

  // Double-click to zoom
  network.on('doubleClick', function(params) {{
    if (params.nodes.length > 0) {{
      network.focus(params.nodes[0], {{ scale: 1.5, animation: true }});
    }}
  }});
}}

// ─── Init ───
document.addEventListener('DOMContentLoaded', initGraph);
</script>
</body>
</html>"""


def build_wikilinks_section(related: list, all_articles: list) -> str:
    """Build the related articles wikilinks section."""
    if not related:
        return ""

    cards = []
    for a in related:
        src = a.get("source", "")
        fg, bg = SOURCE_COLORS.get(src, DEFAULT_COLOR)
        title = esc(a.get("title", "")[:60])
        wikilink = esc(a.get("wikilink", ""))

        cards.append(f"""
    <a href="article.html?id={a['id']}" class="wikilink-card" title="{esc(a.get('title',''))}">
      <div class="wikilink-source" style="background:{fg}"></div>
      <span class="wikilink-text">{title}</span>
      <span class="wikilink-arrow">→</span>
    </a>""")

    return f"""
  <div class="wikilinks-section">
    <div class="wikilinks-title">Related Articles</div>
    <div class="wikilinks-grid">
      {''.join(cards)}
    </div>
  </div>"""


def main():
    init_db()
    print(f"Datagateway — Build Article Viewer ({datetime.now(WIB).strftime('%Y-%m-%d %H:%M WIB')})")
    print("=" * 60)

    articles = get_articles(limit=200)
    if not articles:
        print("No articles found in DB.")
        # Still generate a placeholder
        articles = []

    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)

    # Generate one HTML per article (or at least the first one as demo)
    # For simplicity, we generate ONE article viewer that reads ?id= from URL
    # All articles data is embedded in the page

    # Use the first article as default for demo
    default_id = articles[0]["id"] if articles else "demo"
    html = build_html(articles, default_id)

    outpath = DASHBOARD_DIR / "article.html"
    outpath.write_text(html, encoding="utf-8")
    print(f"  Generated: {outpath} ({len(html):,} bytes)")
    print(f"  Articles embedded: {len(articles)}")
    print(f"  Default article: {default_id}")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
