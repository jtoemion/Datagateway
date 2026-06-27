#!/usr/bin/env python3
"""
Datagateway — Update .md files with full article text from scraped_articles DB.
Replaces RSS summaries with full article content in all .md files.
"""

import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

WIB = timezone(timedelta(hours=7))
REPO_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(REPO_ROOT))
from scripts.database import get_db


def update_md_files(dry_run: bool = False) -> int:
    """Update all .md files with full scraped content. Returns count."""
    db = get_db()
    rows = [dict(r) for r in db.execute("""
        SELECT a.id, a.source, a.title, a.url, a.date, a.category, a.lang,
               a.filepath, a.image_url, a.description,
               s.full_text, s.full_html
        FROM articles a
        LEFT JOIN scraped_articles s ON a.id = s.article_id
        ORDER BY a.filepath
    """).fetchall()]
    db.close()

    updated = 0
    for r in rows:
        fpath = r["filepath"]
        if not fpath:
            continue
        md_path = REPO_ROOT / fpath
        if not md_path.exists():
            continue

        full_text = r["full_text"] or ""
        full_html = r["full_html"] or ""

        # Get the real content
        content = full_text or r.get("description") or ""
        has_full = len(content) > 500  # Meaningful content

        # Format content as markdown paragraphs
        if has_full:
            # Strip HTML if we only have HTML
            if not full_text and full_html:
                text = re.sub(r'<[^>]+>', '', full_html)
                text = re.sub(r'\s+', ' ', text).strip()
            else:
                text = content

            # Split into paragraphs
            paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
            md_body = '\n\n'.join(paragraphs)
            scraped_tag = "true"
        else:
            md_body = full_text or r.get("description") or "Full article not available."
            scraped_tag = "false"

        # Build new content
        date_val = r["date"] if r["date"] else ""
        date_wib_str = datetime.fromisoformat(date_val).astimezone(WIB).strftime('%Y-%m-%d %H:%M WIB') if date_val else ""

        cat = r["category"] or "umum"
        lang = r["lang"] or "id"
        img_url = r["image_url"] or ""

        new_content = f"""---
id: {r['id']}
source: "{r['source']}"
title: "{r['title']}"
url: "{r['url']}"
date: {date_val}
date_wib: {date_wib_str}
category: {cat}
lang: {lang}
image_url: {img_url}
scraped: {scraped_tag}
---

# {r['title']}

{md_body}

---

*Sumber: [{r['source']}]({r['url']})*
"""

        if dry_run:
            print(f"  [{'✓' if has_full else '✗'}] {r['source']:25} {r['id'][:12]} — {len(content):>6} chars")
            continue

        md_path.write_text(new_content, encoding="utf-8")
        updated += 1

    return updated


def main():
    dry = "--dry" in sys.argv or "--dry-run" in sys.argv
    label = " [DRY RUN]" if dry else ""

    print(f"Update MD files{label} — {datetime.now(WIB).strftime('%Y-%m-%d %H:%M WIB')}")
    print("=" * 55)

    count = update_md_files(dry_run=dry)
    print(f"\n{'DRY RUN: Would update' if dry else 'Updated'}: {count} files")

    return 0


if __name__ == "__main__":
    main()
