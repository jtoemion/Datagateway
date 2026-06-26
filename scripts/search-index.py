#!/usr/bin/env python3
"""
Build BM25 search index for all articles.

Usage:
    python3 scripts/search-index.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.database import init_db, get_db
from scripts.search import build_index


def main():
    init_db()

    # Collect full text from scraped_articles + articles
    db = get_db()
    rows = db.execute("""
        SELECT
            a.id,
            a.title,
            a.description as excerpt,
            a.source,
            a.url,
            a.date,
            a.date_wib,
            a.category,
            a.lang,
            a.image_url,
            a.filepath,
            s.full_text
        FROM articles a
        LEFT JOIN scraped_articles s ON a.id = s.article_id
        ORDER BY a.date DESC
    """).fetchall()
    db.close()

    articles = [dict(r) for r in rows]
    print(f"Building BM25 index for {len(articles)} articles...")

    # Ensure data dir exists
    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    build_index(articles, output_dir=data_dir)
    print("Done.")


if __name__ == "__main__":
    main()
