#!/usr/bin/env python3
"""
enrich-metadata.py — SHIM (CODE)
Delegates to enrich.metadata; kept for backward compatibility until all
consumers are updated to the new module path.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.enrich.metadata import enrich_article
from scripts.database import init_db, get_db, get_scraped_article


def main():
    init_db()

    if len(sys.argv) > 1:
        article_id = sys.argv[1]
        print(f"Enriching single article: {article_id}")
        result = enrich_article(article_id)
        if result:
            print(f"  ✓ sections={result['sections']}")
            print(f"  ✓ keywords={result['keywords'][:5]}...")
            print(f"  ✓ word_count={result['word_count']}")
        else:
            print(f"  ✗ No data for {article_id}")
        return

    # Enrich all missing
    db = get_db()
    rows = db.execute("""
        SELECT a.id, a.title, s.full_text, s.full_html
        FROM articles a
        LEFT JOIN scraped_articles s ON a.id = s.article_id
        LEFT JOIN article_metadata m ON a.id = m.article_id
        WHERE m.article_id IS NULL
        ORDER BY a.date DESC
    """).fetchall()
    db.close()

    total = len(rows)
    if total == 0:
        print("All articles already enriched.")
        return

    print(f"Found {total} articles to enrich.\n")
    for i, row in enumerate(rows, 1):
        article_id = row["id"]
        title = (row["title"] or "")[:60]
        scraped = None
        if row["id"]:
            scraped = get_scraped_article(row["id"])
        result = enrich_article(article_id, scraped)
        secs = result.get("sections", [])
        kw = result.get("keywords", [])
        print(f"[{i}/{total}] {article_id} | {secs} | {kw[:3]} | {title}...")

    print(f"\n✓ Enriched {total} articles.")


if __name__ == "__main__":
    main()
