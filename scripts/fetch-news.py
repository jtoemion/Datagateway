#!/usr/bin/env python3
"""
Datagateway — OSINT News Fetcher
Ambil berita dari RSS feeds, simpan sebagai file .md terstruktur.
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
from urllib.parse import urlparse

import requests

WIB = timezone(timedelta(hours=7))

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config.yaml"

# Fallback config inline (biar gak depend PyYAML di awal)
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
NEWS_DIR = REPO_ROOT / "news"
USER_AGENT = "Datagateway/1.0 (OSINT News Aggregator; +https://github.com/jtoemion/Datagateway)"


def slugify(text: str) -> str:
    """Buat slug dari judul artikel."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text[:100].rstrip('-')


def parse_rss_date(date_str: str) -> Optional[datetime]:
    """Parse berbagai format tanggal RSS."""
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


def extract_description(entry: dict) -> str:
    """Extract clean description dari entry."""
    desc = entry.get("description", "") or entry.get("summary", "") or ""
    # Bersihin HTML tags
    desc = re.sub(r'<[^>]+>', '', desc)
    desc = re.sub(r'\s+', ' ', desc).strip()
    return desc[:500]


def fetch_rss(source: dict) -> list[dict]:
    """Fetch dan parse RSS feed."""
    name = source["name"]
    url = source["url"]
    articles = []

    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=30,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [!] {name}: Gagal fetch — {e}")
        return articles

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as e:
        print(f"  [!] {name}: Gagal parse XML — {e}")
        return articles

    # RSS 2.0 → channel/item
    # Atom → feed/entry
    ns = {"atom": "http://www.w3.org/2005/Atom"}

    items = root.findall(".//item") or root.findall(".//atom:entry", ns)

    for item in items:
        # Extract fields
        title = ""
        link = ""
        pub_date = ""
        description = ""
        media_content = ""

        # RSS 2.0
        t = item.find("title")
        if t is not None:
            title = t.text or ""

        l = item.find("link")
        if l is not None:
            link = l.text or ""
            # Atom link punya href attrib
            if not link:
                link = l.get("href", "")

        d = item.find("description")
        if d is not None:
            description = d.text or ""

        pd = item.find("pubDate")
        if pd is not None:
            pub_date = pd.text or ""

        # Media:thumbnail
        mt = item.find(".//{http://search.yahoo.com/mrss/}thumbnail")

        if not title:
            # Atom: title bisa punya text child
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

        if not title:
            continue

        # Parse date
        parsed_date = parse_rss_date(pub_date)
        if parsed_date:
            pub_date_iso = parsed_date.isoformat()
            pub_date_wib = parsed_date.astimezone(WIB).strftime("%Y-%m-%d %H:%M WIB")
        else:
            pub_date_iso = datetime.now(WIB).isoformat()
            pub_date_wib = datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB")

        # Unique ID
        content_id = hashlib.md5(f"{link}{title}".encode()).hexdigest()[:12]

        article = {
            "id": content_id,
            "source": name,
            "title": title.strip(),
            "url": link,
            "description": extract_description({"description": description}),
            "pub_date": pub_date_iso,
            "pub_date_wib": pub_date_wib,
            "category": source.get("category", "umum"),
            "lang": source.get("lang", "id"),
        }

        articles.append(article)

    print(f"  [✓] {name}: {len(articles)} artikel")
    return articles[:MAX_PER_SOURCE]


def save_article(article: dict, date_dir: Path) -> Path:
    """Simpan satu artikel sebagai file .md."""
    date_dir.mkdir(parents=True, exist_ok=True)

    slug = slugify(article["title"])
    fname = f"{article['source'].lower().replace(' ', '-')}_{slug}.md"
    fpath = date_dir / fname

    # Cegah overwrite — skip kalau udah ada
    if fpath.exists():
        return fpath

    # Bersihin title dari CDATA
    title_clean = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', article["title"])

    content = f"""---
id: {article['id']}
source: "{article['source']}"
title: "{title_clean}"
url: "{article['url']}"
date: {article['pub_date']}
date_wib: {article['pub_date_wib']}
category: {article['category']}
lang: {article['lang']}
---

# {title_clean}

**Sumber:** [{article['source']}]({article['url']})  
**Waktu:** {article['pub_date_wib']}  
**Kategori:** {article['category']}

{article['description']}

---

*Diambil otomatis oleh Datagateway pada {datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB")}*
"""

    fpath.write_text(content, encoding="utf-8")
    return fpath


def main():
    print(f"Datagateway — OSINT News Fetch ({datetime.now(WIB).strftime('%Y-%m-%d %H:%M WIB')})")
    print("=" * 60)

    today = datetime.now(WIB).strftime("%Y-%m-%d")
    date_dir = NEWS_DIR / today

    total = 0
    for source in SOURCES:
        print(f"\n  [{source['name']}]")
        articles = fetch_rss(source)
        for art in articles:
            save_article(art, date_dir)
        total += len(articles)
        time.sleep(1)  # Rate limit antar source

    print(f"\n{'=' * 60}")
    print(f"Selesai. {total} artikel disimpan di news/{today}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
