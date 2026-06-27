"""
Datagateway — Extract Gateway (GATEWAY)
Iterate unscraped → extractor → persist to DB.
Imports from fetch.extractor (CODE) and scripts.database.
Retry ≤2 on failure; skip and log on persistent failure.
"""

import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.database import (
    init_db,
    get_db,
    article_save_scraped,
    get_scraped_article,
)
from scripts.fetch.extractor import extract
from scripts.fetch.web_fetcher import fetch as web_fetcher
from scripts.sources.gateway import should_scrape

WIB = timezone(timedelta(hours=7))
MIN_WORD_COUNT = 150
MAX_RETRIES = 2


def get_unscraped_articles() -> list[dict]:
    """Return articles that have no scraped_articles entry, excluding scrape:false sources."""
    db = get_db()
    rows = db.execute("""
        SELECT a.id, a.url, a.title, a.image_url, a.source
        FROM articles a
        LEFT JOIN scraped_articles s ON a.id = s.article_id
        WHERE s.article_id IS NULL
        ORDER BY a.date DESC
    """).fetchall()
    db.close()
    return [dict(r) for r in rows]


def extract_with_retry(article_id: str, url: str, title: str) -> dict:
    """
    Try extractor up to MAX_RETRIES times.
    If result < MIN_WORD_COUNT words, fall back to web_fetcher.
    Returns extracted data dict.
    """
    last_error = ""

    for attempt in range(1, MAX_RETRIES + 2):  # 1..3 (extractor + web_fetcher fallback)
        try:
            if attempt == 1:
                data = extract(url)
            else:
                data = web_fetcher(url)

            word_count = data.get("word_count", 0)

            # If extractor gave us enough content, use it
            if word_count >= MIN_WORD_COUNT:
                return data

            # If extractor failed (< 150 words) and we haven't tried web_fetcher yet
            if attempt == 1 and word_count < MIN_WORD_COUNT:
                last_error = f"extractor low word count ({word_count})"
                continue  # try web_fetcher

            # If web_fetcher also returned low content
            if attempt > 1:
                last_error = f"web_fetcher returned {word_count} words"
                break

        except Exception as e:
            last_error = str(e)
            if attempt < MAX_RETRIES:
                continue
            break

    return {"text": "", "html": "", "author": "", "images": [], "word_count": 0, "error": last_error}


def run() -> dict:
    """
    Run the extraction pipeline.
    Returns {"attempted": int, "succeeded": int, "failed": int}.
    """
    init_db()
    articles = get_unscraped_articles()

    if not articles:
        print("  No unscraped articles found.")
        return {"attempted": 0, "succeeded": 0, "failed": 0}

    print(f"  Found {len(articles)} unscraped articles.")
    succeeded = 0
    failed = 0

    for art in articles:
        article_id = art["id"]
        url = art["url"]
        title = (art["title"] or "")[:60]
        source_name = art.get("source", "")

        # Skip sources configured with scrape: false
        if not should_scrape(source_name):
            print(f"    [SKIP] {article_id} ({title}) from {source_name} — scrape disabled in config")
            # Write a stub so it won't be retried
            article_save_scraped(
                article_id=article_id, url=url, title=title,
                author="", full_html="", full_text="", images=[],
            )
            continue

        data = extract_with_retry(article_id, url, title)
        word_count = data.get("word_count", 0)

        if word_count == 0:
            # Persistent failure — skip
            failed += 1
            print(f"    [FAIL] {article_id} ({title}): {data.get('error', 'unknown error')}")
            continue

        # Save scraped article
        article_save_scraped(
            article_id=article_id,
            url=url,
            title=title,
            author=data.get("author", ""),
            full_html=data.get("html", ""),
            full_text=data.get("text", ""),
            images=data.get("images", []),
        )

        # Update articles.image_url if extractor found images and article has no image
        images = data.get("images", [])
        if images and not art.get("image_url"):
            # Set primary image on the article
            db = get_db()
            db.execute(
                "UPDATE articles SET image_url = ? WHERE id = ? AND image_url = ''",
                (images[0]["src"], article_id),
            )
            db.commit()
            db.close()

        succeeded += 1
        print(f"    [OK] {article_id} ({title}): {word_count} words, {len(images)} images")

    print(f"\n  Extraction: {succeeded}/{len(articles)} succeeded, {failed} failed.")
    return {"attempted": len(articles), "succeeded": succeeded, "failed": failed}


def main():
    print(f"Extract Gateway — {datetime.now(WIB).strftime('%Y-%m-%d %H:%M WIB')}")
    print("=" * 60)
    run()


if __name__ == "__main__":
    main()
