"""
Datagateway — RSS Fetcher (CODE)
RSS → article stubs (id/title/url/date/image).
No content from body. Migrated from fetch-news.py.

Source list is hardcoded here (read by sources/gateway.py).
"""

import hashlib
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import requests

from scripts.database import (
    cache_get,
    cache_set,
    article_exists,
    log_fetch,
)

WIB = timezone(timedelta(hours=7))
USER_AGENT = "Datagateway/1.0 (OSINT News Aggregator; SQLite cache; +https://github.com/jtoemion/Datagateway)"

# Hardcoded RSS sources — consumed by sources/gateway.py
SOURCES = [
    {"name": "CNN Indonesia", "url": "https://www.cnnindonesia.com/rss", "lang": "id", "category": "umum"},
    {"name": "Detik", "url": "https://news.detik.com/rss", "lang": "id", "category": "umum"},
    {"name": "CNBC Indonesia", "url": "https://www.cnbcindonesia.com/rss", "lang": "id", "category": "bisnis"},
    {"name": "Antara", "url": "https://www.antaranews.com/rss/terkini", "lang": "id", "category": "umum"},
    {"name": "Republika", "url": "https://www.republika.co.id/rss", "lang": "id", "category": "umum"},
    {"name": "BBC Indonesia", "url": "https://feeds.bbci.co.uk/indonesia/rss.xml", "lang": "id", "category": "internasional"},
    {"name": "BBC News", "url": "https://feeds.bbci.co.uk/news/rss.xml", "lang": "en", "category": "internasional"},
    {"name": "NY Times", "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "lang": "en", "category": "internasional"},
    # Football RSS (category='football')
    {"name": "BBC Football", "url": "https://feeds.bbci.co.uk/sport/football/rss.xml", "lang": "en", "category": "football"},
    {"name": "Sky Sports Football", "url": "https://www.skysports.com/rss/12040", "lang": "en", "category": "football"},
    {"name": "The Guardian Football", "url": "https://www.theguardian.com/football/rss", "lang": "en", "category": "football"},
    {"name": "Fox Sports Soccer", "url": "https://api.foxsports.com/v1/rss?partnerKey=zBaFxRyGKCfxBagJG9b8MjLy&tag=soccer", "lang": "en", "category": "football"},
    {"name": "NY Times Soccer", "url": "https://rss.nytimes.com/services/xml/rss/nyt/Soccer.xml", "lang": "en", "category": "football"},
]

MAX_PER_SOURCE = 15
CACHE_TTL = 1800  # 30 minutes


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
            cache_set(cache_key, raw, ttl_seconds=CACHE_TTL)
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
        mt = item.find(f".//{{{media_ns}}}thumbnail")
        if mt is not None:
            image_url = mt.get("url", "")
        if not image_url:
            mc = item.find(f".//{{{media_ns}}}content")
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
