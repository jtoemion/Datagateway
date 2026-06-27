"""
Datagateway — Search Indexer (CODE)
BM25 build from DB articles.
Migrated from search-index.py.
"""

import pickle
import json
import re
from pathlib import Path

try:
    from rank_bm25 import BM25Okapi
    _HAS_BM25 = True
except ImportError:
    _HAS_BM25 = False

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
INDEX_PATH = REPO_ROOT / "data" / "search_index.pkl"
ARTICLES_PATH = REPO_ROOT / "data" / "search_articles.pkl"


def _tokenize(text: str) -> list[str]:
    """Simple tokenizer: lowercase, strip punctuation, split on whitespace."""
    if not text:
        return []
    text = re.sub(r"[^\w\s]", " ", text.lower())
    return [t for t in text.split() if len(t) > 1]


def build_index(articles: list[dict], output_dir: Path = None) -> bool:
    """
    Build BM25Okapi index from article list and pickle to disk.

    Returns True if built, False if skipped (no rank_bm25).
    """
    if not _HAS_BM25:
        print("rank_bm25 not installed. Skipping index build.")
        return False

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
        return False

    bm25 = BM25Okapi(corpus)

    with open(INDEX_PATH, "wb") as f:
        pickle.dump(bm25, f)
    with open(ARTICLES_PATH, "wb") as f:
        pickle.dump(article_list, f)

    # Update meta
    from scripts.database import get_db
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('search_index_built_at', datetime('now'))"
    )
    db.commit()
    db.close()

    print(f"  Index: {INDEX_PATH} ({len(corpus)} docs)")
    print(f"  Articles: {ARTICLES_PATH}")
    return True
