"""
Datagateway — RSS Normalize (CODE)
Layer 1 contract: every article exits with normalized_description ≥ 250 chars.

PASSTHROUGH  description already ≥ 250c → stored verbatim
NORMALIZED   description < 250c → AI rewrite using only title + description
STUB         combined input < 60c → too thin to normalize; stored as-is
"""

import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

import anthropic

from scripts.database import (
    get_articles_needing_normalize,
    save_normalized_description,
)

THRESHOLD = 250
STUB_MIN  = 60   # combined title+description chars below which we skip AI

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    return _client


_PROMPT_ID = """\
Kamu adalah editor berita yang berpengalaman. Tulis ulang deskripsi berita di bawah ini menjadi 2-3 kalimat yang padat dan jelas.

ATURAN WAJIB:
- Gunakan HANYA informasi dari Judul dan Deskripsi yang diberikan. Jangan menambahkan fakta baru.
- Atribusikan ke sumber: awali dengan "Menurut {source}, ..."
- Tidak ada opini, spekulasi, atau konteks yang tidak ada di input.
- Bahasa: Bahasa Indonesia. Register: netral dan faktual.
- Panjang target: 250-350 karakter.

Judul: {title}
Sumber: {source}
Deskripsi: {description}

Tulis ulang:"""

_PROMPT_EN = """\
You are an experienced news editor. Rewrite the description below into 2-3 tight, factual sentences.

STRICT RULES:
- Use ONLY information present in the Title and Description. Add no new facts.
- Open with attribution: "According to {source}, ..."
- No opinion, speculation, or context absent from the input.
- Language: English. Register: neutral and factual.
- Target length: 250-350 characters.

Title: {title}
Source: {source}
Description: {description}

Rewrite:"""


def _ai_normalize(title: str, source: str, description: str, lang: str) -> str:
    template = _PROMPT_ID if lang == "id" else _PROMPT_EN
    prompt = template.format(
        title=title.strip(),
        source=source,
        description=description.strip(),
    )
    try:
        resp = _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        print(f"    [normalize] AI error: {e}")
        return ""


def normalize_article(
    article_id: str,
    title: str,
    source: str,
    description: str,
    lang: str,
) -> tuple[str, str]:
    """
    Returns (normalized_description, desc_source).
    Caller is responsible for persisting via save_normalized_description().
    """
    desc = (description or "").strip()

    if len(desc) >= THRESHOLD:
        return desc, "PASSTHROUGH"

    combined = f"{title} {desc}".strip()
    if len(combined) < STUB_MIN:
        return desc, "STUB"

    result = _ai_normalize(title, source, desc, lang)
    if not result:
        return desc, "STUB"

    return result, "NORMALIZED"


def run_normalize_pipeline(max_articles: int = 500) -> dict:
    """
    Process all articles missing normalized_description.
    Returns {processed, passthrough, normalized, stub, errors}.
    """
    from datetime import datetime, timezone, timedelta
    wib = timezone(timedelta(hours=7))
    print(f"Layer 1 — RSS Normalize ({datetime.now(wib).strftime('%Y-%m-%d %H:%M WIB')})")

    articles = get_articles_needing_normalize(limit=max_articles)
    total = len(articles)
    print(f"  Pending: {total} articles")

    counts = {"processed": 0, "passthrough": 0, "normalized": 0, "stub": 0, "errors": 0}

    for art in articles:
        aid   = art["id"]
        title = art["title"] or ""
        src   = art["source"] or ""
        desc  = art["description"] or ""
        lang  = art["lang"] or "id"

        try:
            normalized, tag = normalize_article(aid, title, src, desc, lang)
            save_normalized_description(aid, normalized, tag)
            counts["processed"] += 1
            counts[tag.lower()] += 1

            if tag == "NORMALIZED":
                time.sleep(0.15)  # stay inside 10 req/min Haiku limit

        except Exception as e:
            print(f"    [normalize] {aid}: {e}")
            counts["errors"] += 1

    print(
        f"  Done — passthrough:{counts['passthrough']} "
        f"normalized:{counts['normalized']} "
        f"stub:{counts['stub']} "
        f"errors:{counts['errors']}"
    )
    return counts


if __name__ == "__main__":
    run_normalize_pipeline()
