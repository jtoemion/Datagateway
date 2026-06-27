"""
Datagateway — Sources Gateway (GATEWAY)
Placeholder that reads the hardcoded source list and dispatches to rss or football.
DR-0002 will wire config.yaml next.

Dispatches:
  - category='football' → fetch/football.fetch_events (TheRundown API)
  - otherwise → fetch/rss.fetch_rss (RSS feeds)
"""

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.fetch.rss import SOURCES as RSS_SOURCES, fetch_rss
from scripts.fetch.football import FOOTBALL_SPORTS, fetch_events
from scripts.database import (
    init_db,
    article_upsert,
    article_exists,
    log_fetch,
    cache_clear,
)

WIB = timezone(timedelta(hours=7))
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
NEWS_DIR = REPO_ROOT / "news"


def slugify(text: str) -> str:
    import re
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text[:100].rstrip("-")


def save_article_md(article: dict, date_dir: Path) -> Path | None:
    """Save article as .md file. Skip if exists."""
    date_dir.mkdir(parents=True, exist_ok=True)
    import re

    slug = slugify(article["title"])
    fname = f"{article['source'].lower().replace(' ', '-')}_{slug}.md"
    fpath = date_dir / fname

    if fpath.exists():
        return fpath

    title_clean = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", article["title"])

    content = f"""---
id: {article['id']}
source: "{article['source']}"
title: "{title_clean}"
url: "{article['url']}"
date: {article['date']}
date_wib: {article['date_wib']}
category: {article['category']}
lang: {article['lang']}
---

# {title_clean}

**Sumber:** [{article['source']}]({article['url']})
**Waktu:** {article['date_wib']}
**Kategori:** {article['category']}

{article['description']}

---

*Diambil otomatis oleh Datagateway pada {datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB")}*
"""
    fpath.write_text(content, encoding="utf-8")
    return fpath


def fetch_rss_sources() -> dict:
    """Fetch all RSS sources. Returns {source_name: [articles]}."""
    results = {}
    for source in RSS_SOURCES:
        articles = fetch_rss(source)
        results[source["name"]] = articles
    return results


def fetch_football_sources() -> dict:
    """Fetch all football sources via TheRundown API."""
    now = datetime.now(WIB)
    today = now.strftime("%Y-%m-%d")
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    results = {}
    for sport_id, sport_name in FOOTBALL_SPORTS:
        for date in [today, tomorrow]:
            events = fetch_events(sport_id, sport_name, date)
            if events:
                results[f"{sport_name} ({date})"] = events
                break
    return results


def run() -> dict:
    """
    Run the full sources pipeline.
    Returns {"rss_new": int, "rss_skip": int, "football_events": int}.
    """
    init_db()
    now = datetime.now(WIB)
    today = now.strftime("%Y-%m-%d")
    date_dir = NEWS_DIR / today

    print(f"Sources Gateway — {now.strftime('%Y-%m-%d %H:%M WIB')}")
    print("=" * 60)

    total_new = 0
    total_skip = 0

    # RSS sources
    print("\n  [RSS feeds]")
    rss_results = fetch_rss_sources()
    for source_name, articles in rss_results.items():
        new_count = 0
        for art in articles:
            if article_exists(art["url"]):
                total_skip += 1
                continue

            slug = slugify(art["title"])
            fname = f"{art['source'].lower().replace(' ', '-')}_{slug}.md"
            filepath = f"news/{today}/{fname}"
            art["filepath"] = filepath
            art["wikilink"] = f"[[{filepath}]]"

            article_upsert(art)
            save_article_md(art, date_dir)
            new_count += 1
            total_new += 1

        if new_count > 0:
            log_fetch(source_name, new_count, "ok")

    # Football sources
    print("\n  [Football]")
    football_results = fetch_football_sources()
    football_event_count = sum(len(v) for v in football_results.values())

    cache_clear_count = cache_clear()
    if cache_clear_count:
        print(f"  Cache cleaned: {cache_clear_count} expired entries")

    print(f"\n{'=' * 60}")
    print(f"  New articles: {total_new} | Skipped (dup): {total_skip}")
    print(f"  Football events: {football_event_count}")

    return {
        "rss_new": total_new,
        "rss_skip": total_skip,
        "football_events": football_event_count,
    }


def main():
    run()


if __name__ == "__main__":
    main()
