"""
Datagateway — Enrichment Gateway (GATEWAY)
Orchestrates entity extraction, linking, tagging, and entity page generation.
"""

import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.database import get_db, get_scraped_article
from scripts.enrich.entities import extract_entities
from scripts.enrich.entity_linker import link_entities
from scripts.enrich.tagger import tag_article, write_entity_pages


WIB = timezone(timedelta(hours=7))


def enrich_entity_pipeline(article_id: str = None, max_articles: int = 200) -> dict:
    """
    Run the full entity enrichment pipeline.

    Args:
        article_id: if provided, only enrich this article
        max_articles: max articles to process (default 200)

    Returns:
        {processed, tagged, entity_pages}
    """
    now = datetime.now(WIB)
    print(f"Entity Enrichment — {now.strftime('%Y-%m-%d %H:%M WIB')}")

    db = get_db()

    if article_id:
        rows = db.execute(
            "SELECT a.id, a.title, a.description, a.normalized_description, a.filepath FROM articles a WHERE a.id = ?",
            (article_id,),
        ).fetchall()
    else:
        rows = db.execute(
            """SELECT a.id, a.title, a.description, a.normalized_description, a.filepath
               FROM articles a
               LEFT JOIN article_entities ae ON a.id = ae.article_id
               WHERE ae.article_id IS NULL
               ORDER BY a.date DESC
               LIMIT ?""",
            (max_articles,),
        ).fetchall()
    db.close()

    processed = 0
    tagged = 0

    for r in rows:
        aid = r["id"]
        title = r["title"] or ""
        # prefer Layer 1 output; fall back to raw description
        desc = r["normalized_description"] or r["description"] or ""
        filepath = r["filepath"] or ""

        # Get full text from scraped_articles
        scraped = get_scraped_article(aid)
        text = (scraped.get("full_text") or "") if scraped else ""

        if not text and not title:
            continue

        # 1. Extract raw entities
        raw_entities = extract_entities(title, text, desc)
        if not raw_entities:
            continue

        # 2. Link/resolve entities
        linked = link_entities(raw_entities)

        # 3. Write to article_entities table
        _write_article_entities(aid, linked)

        # 4. Tag .md file with wikilinks
        if filepath:
            md_path = REPO_ROOT / filepath
            if tag_article(md_path, linked):
                tagged += 1

        processed += 1

    # 5. Regenerate entity pages
    entity_pages = write_entity_pages()

    print(f"  Processed: {processed} articles")
    print(f"  Tagged: {tagged} .md files")
    print(f"  Entity pages: {entity_pages}")

    return {"processed": processed, "tagged": tagged, "entity_pages": entity_pages}


def _write_article_entities(article_id: str, linked: list[dict]):
    """Write linked entities to article_entities table."""
    db = get_db()
    for ent in linked:
        db.execute(
            """INSERT OR REPLACE INTO article_entities (article_id, entity_id, mention_count)
               VALUES (?, ?, COALESCE((SELECT mention_count FROM article_entities
                                        WHERE article_id = ? AND entity_id = ?), 0) + 1)""",
            (article_id, ent["entity_id"], article_id, ent["entity_id"]),
        )
    db.commit()
    db.close()


def main():
    import sys
    article_id = sys.argv[1] if len(sys.argv) > 1 else None
    result = enrich_entity_pipeline(article_id=article_id)
    return 0


if __name__ == "__main__":
    main()
