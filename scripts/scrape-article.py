#!/usr/bin/env python3
"""
Article scraper — fetches full HTML article content and extracts text + images.

Usage:
    python3 scripts/scrape-article.py [article_id]   # scrape single article
    python3 scripts/scrape-article.py                # scrape all unscraped articles
"""

import sys
import time
import json
import re
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

# ── project local imports ────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.database import (
    get_db,
    init_db,
    cache_get,
    cache_set,
    article_scraped_exists,
    article_save_scraped,
    save_article_metadata,
)


# ── constants ───────────────────────────────────────────────────────────────
WIB = timezone(timedelta(hours=7))
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; DatagatewayBot/1.0; "
        "+https://github.com/datagateway)"
    ),
    "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
REQUEST_TIMEOUT = 20
STRIP_SELECTORS = [
    "nav", "header", "footer", "aside",
    ".nav", ".navbar", ".menu", ".sidebar", ".widget",
    ".advertisement", ".ad", ".ads", ".sponsored",
    ".social-share", ".share-buttons", ".comments",
    ".related-articles", ".recommended",
    "script", "style", "noscript", "iframe",
    '[role="navigation"]', '[role="banner"]', '[role="contentinfo"]',
]
# Source-specific CSS selectors (ordered by priority for each source)
SOURCE_SELECTORS = {
    "cnnindonesia.com": [
        ("article", None),
        (".article-detail .article-content", None),
        (".article-content", None),
        ("#article", None),
        ("main", None),
    ],
    "detik.com": [
        ("article", None),
        (".detail-content", None),
        (".article__body", None),
        ("#detikdetailtext", None),
        ("main", None),
    ],
    "cnbcindonesia.com": [
        ("article", None),
        (".detail-cnt", None),
        (".content-detail", None),
        ("main", None),
    ],
    "antaranews.com": [
        ("article", None),
        (".post-content", None),
        (".article-content", None),
        ("#post-content", None),
        ("main", None),
    ],
    "republika.co.id": [
        ("article", None),
        (".news-detail", None),
        (".article-content", None),
        (".content", None),
        ("main", None),
    ],
    "bbc.": [
        ("article", None),
        (".bbc-uk8uidix", None),
        (".article-body", None),
        ("[data-component='article-body']", None),
        ("main", None),
    ],
    "nytimes.com": [
        ("article", None),
        (".story-body", None),
        (".article-content", None),
        ("[data-testid='article-body']", None),
        ("main", None),
    ],
}
# Generic fallback selectors (used after source-specific ones)
GENERIC_SELECTORS = [
    ("article", None),
    (".article", None),
    (".post-content", None),
    (".entry-content", None),
    (".content", None),
    ("#content", None),
    ("main", None),
    ("body", None),
]


# ── helpers ──────────────────────────────────────────────────────────────────

def _rate_key(url: str) -> str:
    """Return a rate-limit bucket key based on netloc."""
    return urlparse(url).netloc


class RateLimiter:
    """1 request per second per netloc."""

    def __init__(self):
        self._last: dict[str, float] = {}

    def wait(self, url: str):
        key = _rate_key(url)
        now = time.monotonic()
        if key in self._last:
            elapsed = now - self._last[key]
            if elapsed < 1.0:
                time.sleep(1.0 - elapsed)
        self._last[key] = time.monotonic()


def _clear_url_cache(url: str):
    """Remove the cached HTML for a URL so next fetch uses fresh strategy."""
    cache_key = f"scrape:{hashlib.md5(url.encode()).hexdigest()}"
    db = get_db()
    db.execute("DELETE FROM cache WHERE cache_key = ?", (cache_key,))
    db.commit()
    db.close()


def _fetch_url(url: str, timeout: int = REQUEST_TIMEOUT) -> str | None:
    """Fetch URL with DB-cache check. Returns HTML string or None."""
    # Check DB cache (key = URL hash)
    cache_key = f"scrape:{hashlib.md5(url.encode()).hexdigest()}"
    cached = cache_get(cache_key, ttl_seconds=86400 * 7)  # 7-day cache
    if cached:
        return cached

    # ── 1. Normal fetch ────────────────────────────────────────────────────────
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if resp.status_code == 200 and len(resp.text) > 500:
            resp.encoding = resp.apparent_encoding or "utf-8"
            body = resp.text
            cache_set(cache_key, body, status_code=resp.status_code, ttl_seconds=86400 * 7)
            return body
    except Exception:
        pass

    # ── 2. Jina AI reader fallback (for paywall-blocked sites like NYT) ─────────
    try:
        jina_url = f"https://r.jina.ai/{url}"
        resp = requests.get(
            jina_url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; DatagatewayBot/1.0)",
                "Accept": "text/plain, text/markdown; q=0.9",
                "X-Return-Format": "text",
            },
            timeout=timeout,
        )
        if resp.status_code == 200 and len(resp.text) > 200:
            # Jina returns plain text/markdown — wrap in minimal HTML for compatibility
            text = resp.text.strip()
            body = f"<article>\n<p>" + text.replace("\n\n", "</p>\n<p>") + "</p>\n</article>"
            cache_set(cache_key, body, status_code=resp.status_code, ttl_seconds=86400 * 7)
            return body
    except Exception:
        pass

    # ── 3. readability-lxml fallback ───────────────────────────────────────────
    # Try one more time with readability extraction
    try:
        from readability import Document
        resp = requests.get(url, headers={**HEADERS, "User-Agent": "Mozilla/5.0"}, timeout=timeout)
        if resp.status_code == 200 and len(resp.text) > 1000:
            doc = Document(resp.text)
            html = doc.summary()
            if html and len(html) > 200:
                cache_set(cache_key, html, status_code=resp.status_code, ttl_seconds=86400 * 7)
                return html
    except Exception:
        pass

    return None


def _strip_noise(soup: BeautifulSoup) -> BeautifulSoup:
    """Remove nav, ads, sidebars, scripts, styles from soup in-place."""
    for sel in STRIP_SELECTORS:
        for tag in soup.select(sel):
            tag.decompose()
    return soup


def _extract_images(container) -> list[dict]:
    """Extract all <img> attributes from a soup container."""
    images = []
    for img in container.find_all("img"):
        src = img.get("data-src") or img.get("src") or ""
        # Skip data URIs, logo files, and UI icons
        if not src or src.startswith("data:"):
            continue
        src_lower = src.lower()
        if ("logo.png" in src_lower or "logo.jpg" in src_lower or
            "icon-" in src_lower or "/icons/" in src_lower or
            ".svg" in src_lower and "logo" in src_lower):
            continue
        images.append({
            "src":    src,
            "alt":    img.get("alt", ""),
            "width":  img.get("width", ""),
            "height": img.get("height", ""),
        })
    return images


def _extract_author(soup: BeautifulSoup) -> str:
    """Try multiple selectors to find author/meta."""
    # Meta tags first
    for prop in ("author", "article:author", "twitter:creator"):
        meta = soup.find("meta", {"property": prop}) or soup.find("meta", {"name": prop})
        if meta and meta.get("content"):
            return meta["content"].strip()

    # Common class/id patterns
    for sel in [".author", ".byline", "[class*='author']", "[class*='writer']"]:
        el = soup.select_one(sel)
        if el:
            return el.get_text(strip=True)

    return ""


def _get_selectors(url: str) -> list[tuple]:
    """Return ordered selector list for the given URL."""
    netloc = urlparse(url).netloc
    for domain, selectors in SOURCE_SELECTORS.items():
        if domain in netloc:
            return selectors
    return []


def _extract_content(html: str, url: str) -> tuple[str, str, list[dict]]:
    """
    Extract article content from HTML.
    Returns (cleaned_html, plain_text, images_list).
    """
    soup = BeautifulSoup(html, "lxml")
    _strip_noise(soup)

    selectors = _get_selectors(url) + GENERIC_SELECTORS

    container = None
    for sel, _ in selectors:
        if sel is None:
            continue
        candidates = soup.select(sel)
        for c in candidates:
            # Skip tiny containers
            if len(c.get_text(strip=True)) < 200:
                continue
            container = c
            break
        if container is not None:
            break

    if container is None:
        container = soup.body if soup.body else soup

    # Make a clean copy for HTML output
    clean_soup = BeautifulSoup(str(container), "lxml")
    _strip_noise(clean_soup)

    # Remove any remaining inline scripts/styles
    for tag in clean_soup.find_all(["script", "style", "noscript"]):
        tag.decompose()

    # Remove empty tags
    for tag in clean_soup.find_all(True):
        if not tag.get_text(strip=True) and not tag.find(["img", "a", "br"]):
            tag.decompose()

    full_html = str(clean_soup)
    full_text = clean_soup.get_text(separator="\n", strip=True)
    images = _extract_images(clean_soup)

    return full_html, full_text, images


def scrape_article(article_id: str, url: str, title: str, limiter: RateLimiter) -> bool:
    """Scrape a single article URL and save to database. Returns True on success."""
    print(f"  Scraping: [{article_id}] {title[:60]}...")
    print(f"  URL: {url}")

    limiter.wait(url)
    html = _fetch_url(url)
    if not html:
        print(f"  ✗ FAILED to fetch URL")
        return False

    full_html, full_text, images = _extract_content(html, url)
    author = _extract_author(BeautifulSoup(html, "lxml"))

    article_save_scraped(
        article_id  = article_id,
        url         = url,
        title       = title,
        author      = author,
        full_html   = full_html,
        full_text   = full_text,
        images      = images,
    )
    print(f"  ✓ Done — {len(images)} image(s), {len(full_text)} chars text")

    # Enrich metadata after successful scrape
    # (Run scripts/enrich-metadata.py separately for full batch)

    return True


def scrape_all(force: bool = False):
    """Scrape all articles that haven't been scraped yet. If force=True, re-scrape all."""
    db = get_db()
    if force:
        # Re-scrape all articles (for retry with new fallbacks)
        rows = db.execute("""
            SELECT a.id, a.url, a.title, a.source
            FROM articles a
            ORDER BY a.date DESC
        """).fetchall()
    else:
        rows = db.execute("""
            SELECT a.id, a.url, a.title, a.source
            FROM articles a
            LEFT JOIN scraped_articles s ON a.id = s.article_id
            WHERE s.article_id IS NULL
            ORDER BY a.date DESC
        """).fetchall()
    db.close()

    total = len(rows)
    if total == 0:
        print("No unscraped articles found." if not force else "No articles to re-scrape.")
        return

    print(f"Found {total} article(s). Starting scrape{' (force mode)' if force else ''}...\n")
    limiter = RateLimiter()
    success = 0
    failed = 0
    skipped = 0

    for i, row in enumerate(rows, 1):
        article_id = row["id"]
        url        = row["url"]
        title      = row["title"]
        source     = row["source"]
        print(f"[{i}/{total}] {source}")

        if force:
            # Clear old cache so we can try fresh with new fallbacks
            _clear_url_cache(url)

        ok = scrape_article(article_id, url, title, limiter)
        if ok:
            success += 1
        else:
            failed += 1

    print(f"\n{'='*50}")
    print(f"Scraped: {success}  |  Failed: {failed}  |  Total: {total}")


def main():
    init_db()

    if len(sys.argv) > 1:
        if sys.argv[1] == "--force":
            scrape_all(force=True)
        else:
            article_id = sys.argv[1]
            db = get_db()
            row = db.execute(
                "SELECT id, url, title FROM articles WHERE id = ?", (article_id,)
            ).fetchone()
            db.close()
            if not row:
                print(f"Article '{article_id}' not found in database.")
                sys.exit(1)
            print(f"Single article mode: [{row['id']}] {row['title']}\n")
            # Clear cache for fresh attempt
            _clear_url_cache(row["url"])
            limiter = RateLimiter()
            scrape_article(row["id"], row["url"], row["title"], limiter)
    else:
        scrape_all(force=False)


if __name__ == "__main__":
    main()
