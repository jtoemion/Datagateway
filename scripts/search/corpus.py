"""
Datagateway — Search Corpus Serializer (CODE)
Serializes article corpus + synonym_map as JSON blocks for embedding in dashboard HTML.
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def build_corpus_json(articles: list[dict]) -> str:
    """Serialize article list as compact JSON string for <script> embedding.

    Each article entry includes: id, title, source, url, excerpt,
    date, date_wib, category, lang, image_url, filepath, sections, keywords.
    """
    corpus = []
    for a in articles:
        corpus.append({
            "i": a.get("id", ""),
            "t": a.get("title", ""),
            "s": a.get("source", ""),
            "u": a.get("url", ""),
            "e": (a.get("excerpt") or "")[:300],
            "d": a.get("date", ""),
            "dw": a.get("date_wib", ""),
            "c": a.get("category", ""),
            "l": a.get("lang", ""),
            "img": a.get("image_url", ""),
            "fp": a.get("filepath", ""),
            "kw": a.get("keywords", []),
            "sec": a.get("sections", []),
        })
    return json.dumps(corpus, ensure_ascii=False)


def load_synonym_map() -> dict[str, list[str]]:
    """Load synonym_map.json if it exists, else return default map."""
    path = REPO_ROOT / "data" / "synonym_map.json"
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def build_synonym_json() -> str:
    """Serialize synonym_map as compact JSON for script embedding."""
    sm = load_synonym_map()
    return json.dumps(sm, ensure_ascii=False)
