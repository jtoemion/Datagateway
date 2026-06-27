#!/usr/bin/env python3
"""
auto-meta.py — SHIM (CODE)
Delegates to enrich.auto; kept for backward compatibility until all
consumers are updated to the new module path.
"""

import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.enrich.auto import enrich_article as _auto_enrich
from scripts.database import get_db

WIB = timezone(timedelta(hours=7))
REPO_ROOT = Path(__file__).resolve().parent.parent


def enrich_article(article_id: str, title: str = "", description: str = "",
                   full_text: str = "", full_html: str = "") -> dict:
    """Proxy to the new enrich.auto.enrich_article."""
    return _auto_enrich(article_id, title, description, full_text, full_html)


def enrich_all_missing(silent: bool = False) -> int:
    """Enrich all articles missing metadata. Returns count."""
    db = get_db()
    rows = db.execute("""
        SELECT a.id, a.title, a.description, s.full_text, s.full_html
        FROM articles a
        LEFT JOIN scraped_articles s ON a.id = s.article_id
        LEFT JOIN article_metadata m ON a.id = m.article_id
        WHERE m.article_id IS NULL
    """).fetchall()
    db.close()

    count = 0
    for row in rows:
        art = row["id"]
        title = row["title"] or ""
        desc = row["description"] or ""
        full_text = row["full_text"] or ""
        full_html = row["full_html"] or ""
        _auto_enrich(art, title, desc, full_text, full_html)
        count += 1
        if not silent:
            print(f"  [{count}] {art[:12]} enriched")

    if not silent:
        print(f"  → {count} articles enriched")
    return count


def watch_news(directory: Path = None, interval: int = 60):
    """Watch news/ directory for new .md files and auto-enrich."""
    if directory is None:
        directory = REPO_ROOT / "news"

    print(f"Watching {directory} for new articles (interval={interval}s)...")
    seen = set()
    for f in directory.rglob("*.md"):
        seen.add(f.name)

    try:
        while True:
            new_files = []
            for f in directory.rglob("*.md"):
                if f.name not in seen:
                    new_files.append(f)
                    seen.add(f.name)

            for f in new_files:
                art_id = f.stem.split("_")[0]
                print(f"  New: {f.name}")
                _auto_enrich(art_id)
                print(f"    ✓ enriched")

            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n  Watcher stopped.")


def main():
    if "--watch" in sys.argv:
        watch_news()
        return

    if "--pipeline" in sys.argv:
        count = enrich_all_missing(silent=True)
        print(f"auto-meta: {count} enriched")
        return

    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        art_id = sys.argv[1]
        print(f"Enriching {art_id}...")
        result = _auto_enrich(art_id)
        print(f"  sections: {result['sections']}")
        print(f"  keywords: {result['keywords'][:5]}")
        print(f"  entities: {result['entities'][:5]}")
        print(f"  words: {result['word_count']} (~{result['reading_time']} min)")
        return

    # Default: enrich all missing
    print(f"Auto Metadata Generator — {datetime.now(WIB).strftime('%Y-%m-%d %H:%M WIB')}")
    print("=" * 50)
    enrich_all_missing()


if __name__ == "__main__":
    main()
