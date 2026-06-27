"""
Datagateway — Extractor (CODE)
Trafilatura-based content + image extraction.
extract(url) → {text, html, author, images: [{src, alt}], word_count}

Image rules: empty-alt blocklist, hero-dedup, cap 8 images.
"""

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import trafilatura
import requests

USER_AGENT = (
    "Datagateway/1.0 (content extraction; "
    "+https://github.com/jtoemion/Datagateway)"
)

# Domains that are known to have paywalls or require special handling
SKIP_DOMAINS = {"nytimes.com", "ft.com", "wsj.com", "theguardian.com"}

# Blocked image sources (ad/tracking pixels)
IMAGE_BLOCKLIST = {
    "googlesyndication", "googleadservices", "doubleclick",
    "facebook.com/tr", "connect.facebook.net",
    "analytics", "pixel", "beacon", "tracking",
    "amazon-adsystem", "adnxs", "criteo",
    "scorecardresearch", "quantserve",
}

# Hero image candidates to deduplicate against
HERO_DEDUP_PATTERNS = (
    "hero", "lead", "header", "banner", "featured",
    "og:image", "twitter:image", "share",
)


def _is_blocked_image(src: str) -> bool:
    """Return True if image src is an ad/tracking pixel."""
    src_lower = src.lower()
    return any(b in src_lower for b in IMAGE_BLOCKLIST)


def _is_hero_dup(src: str, alt: str) -> bool:
    """Return True if image looks like a hero/duplicate."""
    src_lower = src.lower()
    alt_lower = (alt or "").lower()
    # If alt text is a generic placeholder, treat as hero dup
    generic_alts = {"image", "photo", "picture", "img", "thumbnail", "pic"}
    if alt_lower in generic_alts:
        return True
    # If src has hero-pattern and is very large (likely the main image)
    if any(p in src_lower for p in HERO_DEDUP_PATTERNS):
        return True
    return False


def _build_images(result) -> list[dict]:
    """
    Extract images from trafilatura result.
    Applies: empty-alt blocklist, hero-dedup, cap 8.
    """
    images = []
    seen_srcs = set()

    # trafilatura puts images in result.images as list of dicts
    # {src, alt} or just strings depending on version
    raw_images = getattr(result, "images", []) or []

    for img in raw_images:
        if len(images) >= 8:
            break

        if isinstance(img, dict):
            src = img.get("src", "")
            alt = img.get("alt", "")
        elif isinstance(img, str):
            src = img
            alt = ""
        else:
            continue

        if not src:
            continue
        if src in seen_srcs:
            continue
        if _is_blocked_image(src):
            continue

        # Skip empty-alt images that look like decorative pixels
        if not alt.strip() and len(images) > 0:
            # First image can be empty-alt if it's the hero
            pass  # allow through, dedup handles it
        elif not alt.strip() and len(images) == 0:
            # First image with empty alt - allow, but flag for dedup
            pass

        if _is_hero_dup(src, alt):
            # If we already have a hero, skip this duplicate
            continue

        seen_srcs.add(src)
        images.append({"src": src, "alt": alt or ""})

    return images


def extract(url: str, timeout: int = 30) -> dict:
    """
    Extract article content from URL using trafilatura.

    Returns:
        {
            "text": str,      # plain text content
            "html": str,      # original or reconstructed HTML
            "author": str,    # author name if found
            "images": list,   # [{src, alt}] max 8, filtered
            "word_count": int,
        }

    On failure, returns {"text": "", "html": "", "author": "", "images": [], "word_count": 0}.
    """
    # Check blocklist domains
    host = ""
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        pass

    if any(skd in host for skd in SKIP_DOMAINS):
        return {"text": "", "html": "", "author": "", "images": [], "word_count": 0}

    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            allow_redirects=True,
        )
        resp.raise_for_status()
        downloaded = resp.text
    except Exception:
        return {"text": "", "html": "", "author": "", "images": [], "word_count": 0}

    if not downloaded:
        return {"text": "", "html": "", "author": "", "images": [], "word_count": 0}

    # Extract with trafilatura — get HTML for image parsing
    result = trafilatura.extract(
        downloaded,
        output_format="json",
        include_comments=False,
        include_images=True,
        include_tables=True,
        favor_precision=True,
    )

    if not result:
        # Fallback: try raw extraction
        result = trafilatura.extract(
            downloaded,
            output_format="json",
            favor_recall=True,
        )
        if not result:
            return {"text": "", "html": downloaded, "author": "", "images": [], "word_count": 0}

    import json

    try:
        data = json.loads(result) if isinstance(result, str) else result
    except (json.JSONDecodeError, TypeError):
        return {"text": "", "html": downloaded, "author": "", "images": [], "word_count": 0}

    text = data.get("text", "") or ""
    html = data.get("html", "") or downloaded
    author = data.get("author", "") or ""
    images_raw = data.get("images", []) or []

    word_count = len(text.split()) if text else 0

    # Build filtered image list
    images = _build_images(images_raw if isinstance(images_raw, list) else [])

    # Also check raw HTML for any images trafilatura missed
    if len(images) == 0:
        import re
        from urllib.parse import urlparse, urljoin
        base_url = url
        for match in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>', html, re.IGNORECASE):
            if len(images) >= 8:
                break
            src = match.group(1)
            if not src or src.startswith("data:"):
                continue
            # Make absolute URL
            if not src.startswith(("http://", "https://")):
                src = urljoin(base_url, src)
            alt_match = re.search(r'alt=["\']([^"\']*)["\']', match.group(0), re.IGNORECASE)
            alt = alt_match.group(1) if alt_match else ""
            if _is_blocked_image(src):
                continue
            seen_srcs = {i["src"] for i in images}
            if src not in seen_srcs:
                images.append({"src": src, "alt": alt or ""})

    return {
        "text": text,
        "html": html,
        "author": author,
        "images": images,
        "word_count": word_count,
    }
