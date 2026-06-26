#!/usr/bin/env python3
"""
Datagateway — OSINT News Fetcher
Ambil berita dari RSS feeds dengan SQLite cache.
Cached 30 menit — hemat kuota API.
"""

import hashlib
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import requests

from scripts.database import (
    init_db,
    cache_get,
    cache_set,
    article_upsert,
    article_exists,
    log_fetch,
    cache_clear,
)

WIB = timezone(timedelta(hours=7))
REPO_ROOT = Path(__file__).resolve().parent.parent
NEWS_DIR = REPO_ROOT / "news"

# Source config — sync with config.yaml
SOURCES = [
    {"name": "CNN Indonesia", "url": "https://www.cnnindonesia.com/rss", "lang": "id", "category": "umum"},
    {"name": "Detik", "url": "https://news.detik.com/rss", "lang": "id", "category": "umum"},
    {"name": "CNBC Indonesia", "url": "https://www.cnbcindonesia.com/rss", "lang": "id", "category": "bisnis"},
    {"name": "Antara", "url": "https://www.antaranews.com/rss/terkini", "lang": "id", "category": "umum"},
    {"name": "Republika", "url": "https://www.republika.co.id/rss", "lang": "id", "category": "umum"},
    {"name": "BBC Indonesia", "url": "https://feeds.bbci.co.uk/indonesia/rss.xml", "lang": "id", "category": "internasional"},
    {"name": "BBC News", "url": "https://feeds.bbci.co.uk/news/rss.xml", "lang": "en", "category": "internasional"},
    {"name": "NY Times", "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "lang": "en", "category": "internasional"},
]

MAX_PER_SOURCE = 15
CACHE_TTL = 1800  # 30 minutes
USER_AGENT = "Datagateway/1.0 (OSINT News Aggregator; SQLite cache; +https://github.com/jtoemion/Datagateway)"


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text[:100].rstrip('-')


def parse_rss_date(date_str: str) -> Optional[datetime]:
    if not date_str:
        return None
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


def clean_html(html_text: str) -> str:
    desc = re.sub(r'<[^>]+>', '', html_text)
    desc = re.sub(r'\s+', ' ', desc).strip()
    return desc[:500]


def fetch_rss(source: dict) -> list[dict]:
    """Fetch RSS feed with SQLite caching. Returns article dicts."""
    name = source["name"]
    url = source["url"]
    cache_key = f"rss:{url}"

    # Check cache first
    cached = cache_get(cache_key, ttl_seconds=CACHE_TTL)
    if cached:
        raw = cached
        from_cache = True
    else:
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=30,
            )
            resp.raise_for_status()
            raw = resp.text
            # Store in cache
            cache_set(cache_key, raw)
            from_cache = False
        except requests.RequestException as e:
            print(f"  [!] {name}: Fetch gagal — {e}")
            log_fetch(name, 0, "error", str(e))
            return []

    # Parse XML
    try:
        root = ET.fromstring(raw.encode("utf-8"))
    except ET.ParseError as e:
        print(f"  [!] {name}: Parse gagal — {e}")
        log_fetch(name, 0, "error", f"ParseError: {e}")
        # If parse failed but was cached, retry fresh
        if from_cache:
            print(f"      → Cache corrupted, skip")
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    items = root.findall(".//item") or root.findall(".//atom:entry", ns)

    articles = []
    for item in items:
        title = ""
        link = ""
        pub_date = ""
        description = ""

        t = item.find("title")
        if t is not None:
            title = t.text or ""

        l = item.find("link")
        if l is not None:
            link = l.text or ""
            if not link:
                link = l.get("href", "")

        d = item.find("description")
        if d is not None:
            description = d.text or ""

        pd = item.find("pubDate")
        if pd is not None:
            pub_date = pd.text or ""

        # Image from RSS media:thumbnail, media:content, or enclosure
        image_url = ""
        media_ns = "http://search.yahoo.com/mrss/"
        mt = item.find(f"./{{{media_ns}}}thumbnail")
        if mt is not None:
            image_url = mt.get("url", "")
        if not image_url:
            mc = item.find(f"./{{{media_ns}}}content")
            if mc is not None and mc.get("medium") in ("image", None):
                image_url = mc.get("url", "")
        if not image_url:
            enc = item.find("enclosure")
            if enc is not None and enc.get("type", "").startswith("image"):
                image_url = enc.get("url", "")
        # Extract from description fallback
        if not image_url and description:
            m = re.search(r'<img[^>]+src="([^"]+)"', description)
            if m:
                image_url = m.group(1)

        # Atom fallback
        if not title:
            t_atom = item.find("atom:title", ns)
            if t_atom is not None and t_atom.text:
                title = t_atom.text
        if not pub_date:
            pd_atom = item.find("atom:published", ns) or item.find("atom:updated", ns)
            if pd_atom is not None and pd_atom.text:
                pub_date = pd_atom.text
        if not description:
            desc_atom = item.find("atom:summary", ns) or item.find("atom:content", ns)
            if desc_atom is not None and desc_atom.text:
                description = desc_atom.text

        if not title or not link:
            continue

        parsed_date = parse_rss_date(pub_date)
        if parsed_date:
            pub_date_iso = parsed_date.isoformat()
            pub_date_wib = parsed_date.astimezone(WIB).strftime("%Y-%m-%d %H:%M WIB")
        else:
            pub_date_iso = datetime.now(WIB).isoformat()
            pub_date_wib = datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB")

        content_id = hashlib.md5(f"{link}{title}".encode()).hexdigest()[:12]

        articles.append({
            "id": content_id,
            "source": name,
            "title": title.strip(),
            "url": link,
            "image_url": image_url,
            "description": clean_html(description),
            "date": pub_date_iso,
            "date_wib": pub_date_wib,
            "category": source.get("category", "umum"),
            "lang": source.get("lang", "id"),
        })

    # Dedup by URL
    seen = set()
    unique = []
    for a in articles:
        if a["url"] not in seen:
            seen.add(a["url"])
            unique.append(a)

    cache_label = "cached" if from_cache else "fresh"
    print(f"  [✓] {name}: {len(unique)}/{len(articles)} artikel ({cache_label})")
    return unique[:MAX_PER_SOURCE]


def save_article_md(article: dict, date_dir: Path) -> Path | None:
    """Save article as .md file. Skip if exists."""
    date_dir.mkdir(parents=True, exist_ok=True)

    slug = slugify(article["title"])
    fname = f"{article['source'].lower().replace(' ', '-')}_{slug}.md"
    fpath = date_dir / fname

    if fpath.exists():
        return fpath

    title_clean = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', article["title"])

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


def main():
    init_db()
    print(f"Datagateway — OSINT News Fetch ({datetime.now(WIB).strftime('%Y-%m-%d %H:%M WIB')})")
    print(f"  DB: {REPO_ROOT / 'datagateway.db'}")
    print(f"  Cache TTL: {CACHE_TTL//60} menit")
    print("=" * 60)

    today = datetime.now(WIB).strftime("%Y-%m-%d")
    date_dir = NEWS_DIR / today

    total_new = 0
    total_cache = 0
    total_skip = 0

    for source in SOURCES:
        print(f"\n  [{source['name']}]")
        articles = fetch_rss(source)

        new_count = 0
        for art in articles:
            # Skip if URL already in DB
            if article_exists(art["url"]):
                total_skip += 1
                continue

            # Generate wikilink/filepath
            slug = slugify(art["title"])
            fname = f"{art['source'].lower().replace(' ', '-')}_{slug}.md"
            filepath = f"news/{today}/{fname}"
            art["filepath"] = filepath
            art["wikilink"] = f"[[{filepath}]]"

            # Simpan ke SQLite
            article_upsert(art)

            # Simpan .md file
            save_article_md(art, date_dir)

            new_count += 1

        total_new += new_count
        if new_count > 0:
            log_fetch(source["name"], new_count, "ok")

        time.sleep(1)  # Rate limit antar source

    print(f"\n{'=' * 60}")
    print(f"  New: {total_new} | Skipped (dup): {total_skip} | Total in DB: TODO")
    print(f"  MD files: news/{today}/")
    cache_clear_count = cache_clear()
    if cache_clear_count:
        print(f"  Cache cleaned: {cache_clear_count} expired entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
