#!/usr/bin/env python3
"""
Datagateway — Backfill article images from og:image meta tags.
Also updates scraped_articles with full-page images.
"""

import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from scripts.database import get_db, cache_get, cache_set

WIB = timezone(timedelta(hours=7))
USER_AGENT = "Datagateway/1.0 (Image Backfill; +https://github.com/jtoemion/Datagateway)"
CACHE_TTL = 86400 * 7  # 7 days


def extract_og_image(html: str) -> str:
    """Extract og:image from HTML meta tags."""
    m = re.search(r'<meta\s+property="og:image"[^>]+content="([^"]+)"', html, re.I)
    if m:
        return m.group(1)
    m = re.search(r'<meta\s+name="twitter:image"[^>]+content="([^"]+)"', html, re.I)
    if m:
        return m.group(1)
    return ""


def extract_first_image(html: str) -> str:
    """Extract first <img> src from HTML."""
    m = re.search(r'<img[^>]+src="([^"]+)"', html)
    if m:
        src = m.group(1)
        # Filter out small icons
        if "icon" not in src.lower() and "logo" not in src.lower() and "spacer" not in src.lower():
            return src
    return ""


def backfill_images(force: bool = False):
    """Backfill image_url for articles missing it."""
    db = get_db()

    if force:
        rows = db.execute("SELECT id, url FROM articles").fetchall()
    else:
        rows = db.execute("SELECT id, url FROM articles WHERE image_url IS NULL OR image_url = ''").fetchall()

    total = len(rows)
    print(f"Backfilling images for {total} articles...")
    print(f"{'='*60}")

    updated = 0
    for i, row in enumerate(rows, 1):
        aid = row["id"]
        url = row["url"]
        print(f"  [{i}/{total}] {aid[:12]}... ", end="", flush=True)

        cache_key = f"ogimg:{aid}"
        cached = cache_get(cache_key, ttl_seconds=CACHE_TTL)
        if cached:
            print(f"cached: {cached[:60]}...")
            if cached:
                db.execute("UPDATE articles SET image_url = ? WHERE id = ?", (cached, aid))
                updated += 1
            continue

        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            print(f"fetch fail: {e}")
            cache_set(cache_key, "", ttl_seconds=CACHE_TTL)
            continue

        img = extract_og_image(html)
        if not img:
            img = extract_first_image(html)

        if img:
            # Make absolute URL
            parsed = urlparse(url)
            if img.startswith("//"):
                img = f"{parsed.scheme}:{img}"
            elif img.startswith("/"):
                img = f"{parsed.scheme}://{parsed.netloc}{img}"
            elif not img.startswith("http"):
                img = f"{parsed.scheme}://{parsed.netloc}/{img.lstrip('/')}"

            db.execute("UPDATE articles SET image_url = ? WHERE id = ?", (img, aid))
            cache_set(cache_key, img, ttl_seconds=CACHE_TTL)
            updated += 1
            print(f"✓ {img[:70]}...")
        else:
            # Also extract images from scraped_articles full_html
            sa = db.execute("SELECT full_html FROM scraped_articles WHERE article_id = ?", (aid,)).fetchone()
            if sa and sa["full_html"]:
                soup = BeautifulSoup(sa["full_html"], "html.parser")
                imgs = soup.find_all("img")
                for img_tag in imgs:
                    src = img_tag.get("src", "")
                    if src and "icon" not in src.lower() and "logo" not in src.lower():
                        db.execute("UPDATE articles SET image_url = ? WHERE id = ?", (src, aid))
                        updated += 1
                        print(f"✓ (from html) {src[:70]}...")
                        break
                else:
                    cache_set(cache_key, "", ttl_seconds=CACHE_TTL)
                    print("✗ no image found")
            else:
                cache_set(cache_key, "", ttl_seconds=CACHE_TTL)
                print("✗ no image found")

        time.sleep(0.3)

    db.commit()
    db.close()
    print(f"\n{'='*60}")
    print(f"Updated: {updated}/{total} articles with images")


def main():
    print(f"Datagateway — Image Backfill ({datetime.now(timezone(timedelta(hours=7))).strftime('%Y-%m-%d %H:%M WIB')})")
    force = "--force" in sys.argv
    backfill_images(force=force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
