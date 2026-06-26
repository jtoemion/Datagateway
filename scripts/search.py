#!/usr/bin/env python3
"""
BM25 search module — provides full-text search with synonym expansion.

Usage:
    from scripts.search import search_articles, search_with_synonyms, suggest_synonyms
"""

import pickle
import json
import re
from pathlib import Path
from typing import Optional

try:
    from rank_bm25 import BM25Okapi
    _HAS_BM25 = True
except ImportError:
    _HAS_BM25 = False


REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = REPO_ROOT / "data" / "search_index.pkl"
ARTICLES_PATH = REPO_ROOT / "data" / "search_articles.pkl"
SYNONYM_PATH = REPO_ROOT / "data" / "synonym_map.json"

# Default synonym map (inline, same as enrich-metadata.py)
DEFAULT_SYNONYMS = {
    "AS": ["Amerika Serikat", "United States", "USA", "U.S.", "America"],
    "RI": ["Indonesia", "Republik Indonesia", "NKRI"],
    "UK": ["Inggris", "United Kingdom", "Britain", "Great Britain", "GB"],
    "UAE": ["Uni Emirat Arab", "United Arab Emirates", "Emirat", "Dubai"],
    "Korsel": ["Korea Selatan", "South Korea", "ROK"],
    "Korut": ["Korea Utara", "North Korea", "DPRK"],
    "RRT": ["Republik Rakyat Tiongkok", "China", "Tiongkok", "PRC"],
    "Prabowo": ["Presiden Prabowo", "Prabowo Subianto", "Menhan"],
    "Gibran": ["Gibran Rakabuming", "Wapres", "Wakil Presiden"],
    "Mega": ["Megawati", "Megawati Sukarnoputri", "PDI-P"],
    "Jkw": ["Joko Widodo", "Jokowi", "President Jokowi"],
    "PDIP": ["PDI-P", "PDI Perjuangan"],
    "Golkar": ["Partai Golkar"],
    "Gerindra": ["Partai Gerinda"],
    "Nasdem": ["Partai NasDem"],
    "PKS": ["Partai Keadilan Sejahtera"],
    "PKB": ["Partai Kebangkitan Bangsa"],
    "DPR": ["Dewan Perwakilan Rakyat"],
    "DPRD": ["DPRD Provinsi", "DPRD Kota"],
    "MK": ["Mahakam Konstitusi"],
    "KPK": ["Komisi Pemberantasan Korupsi"],
    "BNN": ["Badan Narkotika Nasional"],
    "POLRI": ["Kepolisian Republik Indonesia"],
    "TNI": ["Tentara Nasional Indonesia"],
    "US$": ["dollar AS", "dolar AS", "US dollar", "USD"],
    "Rp": ["Rupiah", "IDR"],
}

# Global cached objects
_bm25: Optional["BM25Okapi"] = None
_articles: list[dict] = []
_synonym_map: dict[str, list[str]] = {}


def _load_index():
    """Load BM25 index and article list from pickle files."""
    global _bm25, _articles, _synonym_map
    if _bm25 is not None:
        return

    if not _HAS_BM25:
        return

    if INDEX_PATH.exists() and ARTICLES_PATH.exists():
        try:
            with open(INDEX_PATH, "rb") as f:
                _bm25 = pickle.load(f)
            with open(ARTICLES_PATH, "rb") as f:
                _articles = pickle.load(f)
        except Exception:
            _bm25 = None
            _articles = []
            return

    # Load synonym map
    if SYNONYM_PATH.exists():
        try:
            with open(SYNONYM_PATH, "r", encoding="utf-8") as f:
                _synonym_map = json.load(f)
        except Exception:
            _synonym_map = DEFAULT_SYNONYMS.copy()
    else:
        _synonym_map = DEFAULT_SYNONYMS.copy()


def _tokenize(text: str) -> list[str]:
    """Simple tokenizer: lowercase, strip punctuation, split on whitespace."""
    if not text:
        return []
    text = re.sub(r"[^\w\s]", " ", text.lower())
    return [t for t in text.split() if len(t) > 1]


def suggest_synonyms(query: str) -> list[str]:
    """Expand query with synonyms from synonym_map."""
    _load_index()
    tokens = _tokenize(query)
    expanded = list(tokens)
    for tok in tokens:
        # Check if token is a key or value in synonym_map
        if tok in _synonym_map:
            expanded.extend(_synonym_map[tok])
        else:
            # Check if token is a value → also include the key
            for key, values in _synonym_map.items():
                if tok.lower() in [v.lower() for v in values]:
                    expanded.append(key)
    # Deduplicate while preserving order
    seen = set()
    result = []
    for t in expanded:
        if t.lower() not in seen:
            seen.add(t.lower())
            result.append(t)
    return result


def search_articles(query: str, top_k: int = 10) -> list[dict]:
    """
    Full-text search using BM25. Returns ranked article dicts.
    Falls back to simple in-memory search if rank_bm25 not available.
    """
    _load_index()

    if not query:
        return []

    # Try BM25 first
    if _bm25 is not None and _HAS_BM25:
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []
        scores = _bm25.get_scores(query_tokens)
        # Get top-k indices sorted by score descending
        top_indices = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]
        results = []
        for idx, score in top_indices:
            if score <= 0:
                continue
            art = _articles[idx]
            art = dict(art)
            art["_score"] = round(score, 4)
            results.append(art)
        return results

    # Fallback: simple text match scoring
    q_lower = query.lower()
    results = []
    for art in _articles:
        text = f"{art.get('title','')} {art.get('excerpt','')} {art.get('full_text','')}".lower()
        score = 0
        for tok in q_lower.split():
            score += text.count(tok) * 1.0
        if score > 0:
            art = dict(art)
            art["_score"] = score
            results.append(art)
    results.sort(key=lambda x: x["_score"], reverse=True)
    return results[:top_k]


def search_with_synonyms(query: str, top_k: int = 10) -> list[dict]:
    """Search with automatic synonym expansion."""
    expanded = suggest_synonyms(query)
    expanded_query = " ".join(expanded)
    return search_articles(expanded_query, top_k=top_k)


def build_index(articles: list[dict], output_dir: Path = None):
    """
    Build BM25Okapi index from article list and pickle to disk.
    Also saves synonym_map.json.
    """
    if not _HAS_BM25:
        print("rank_bm25 not installed. Skipping index build.")
        return

    if output_dir is None:
        output_dir = REPO_ROOT / "data"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Prepare tokenized corpus
    corpus = []
    article_list = []
    for art in articles:
        title = art.get("title", "") or ""
        excerpt = art.get("excerpt", "") or ""
        full_text = art.get("full_text", "") or ""
        combined = f"{title} {excerpt} {full_text}"
        tokens = _tokenize(combined)
        corpus.append(tokens)
        # Store a lightweight copy
        article_list.append({
            "id": art.get("id"),
            "title": title,
            "source": art.get("source"),
            "url": art.get("url"),
            "excerpt": excerpt[:200],
            "date": art.get("date"),
            "date_wib": art.get("date_wib"),
            "category": art.get("category"),
            "lang": art.get("lang"),
            "image_url": art.get("image_url"),
            "filepath": art.get("filepath"),
        })

    if not corpus:
        print("No articles to index.")
        return

    bm25 = BM25Okapi(corpus)
    doc_count = len(corpus)

    with open(INDEX_PATH, "wb") as f:
        pickle.dump(bm25, f)
    with open(ARTICLES_PATH, "wb") as f:
        pickle.dump(article_list, f)

    # Save synonym map
    syn_path = output_dir / "synonym_map.json"
    with open(syn_path, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_SYNONYMS, f, ensure_ascii=False, indent=2)

    # Update meta
    from scripts.database import get_db
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('search_index_built_at', datetime('now'))"
    )
    db.commit()
    db.close()

    print(f"  Index: {INDEX_PATH} ({doc_count} docs)")
    print(f"  Articles: {ARTICLES_PATH}")
    print(f"  Synonyms: {syn_path}")
