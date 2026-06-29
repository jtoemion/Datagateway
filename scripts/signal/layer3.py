"""
Datagateway — Layer 3: Arc Maturation (GATEWAY)
Maps DEVELOPING arcs → articles, fetches unscraped article bodies,
advances arc lifecycle to FETCH_READY when ≥ MIN_FULL_TEXT articles available.

Lifecycle:  EMERGING → DEVELOPING → FETCH_READY → CONCLUDED
                 ↑Layer 2          ↑Layer 3       ↑Layer 4
"""

import sys
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.database import (
    get_db,
    get_developing_arcs,
    get_arc_articles,
    upsert_arc_article,
    advance_arc_status,
    article_save_scraped,
)
from scripts.sources.gateway import should_scrape

WIB         = timezone(timedelta(hours=7))
MIN_FULL_TEXT = 3    # full-text articles needed before arc is FETCH_READY
FETCH_DELAY   = 0.3  # seconds between HTTP fetches


def _find_arc_article_ids(arc_id: int, entity_spine: str) -> list[str]:
    """
    Resolve entity spine → article IDs that mention ALL spine entities.
    Spine format: "Entity A × Entity B"
    """
    entity_names = [e.strip() for e in entity_spine.split("×")]
    if not entity_names:
        return []

    db = get_db()

    # Resolve canonical names → entity IDs
    entity_ids = []
    for name in entity_names:
        row = db.execute(
            "SELECT id FROM entities WHERE canonical = ?", (name,)
        ).fetchone()
        if row:
            entity_ids.append(row["id"])

    if not entity_ids:
        db.close()
        return []

    if len(entity_ids) == 1:
        rows = db.execute(
            "SELECT DISTINCT article_id FROM article_entities WHERE entity_id = ?",
            (entity_ids[0],),
        ).fetchall()
    else:
        # Articles that mention ALL spine entities (intersection)
        placeholders = ",".join("?" * len(entity_ids))
        rows = db.execute(
            f"""SELECT article_id
                FROM article_entities
                WHERE entity_id IN ({placeholders})
                GROUP BY article_id
                HAVING COUNT(DISTINCT entity_id) = ?""",
            entity_ids + [len(entity_ids)],
        ).fetchall()

    db.close()
    return [r["article_id"] for r in rows]


def _fetch_article(article_id: str, url: str, title: str, source: str) -> bool:
    """
    Fetch full text for one article. Returns True on success.
    Uses extract_gateway's retry logic.
    """
    from scripts.fetch.extract_gateway import extract_with_retry

    if not should_scrape(source):
        article_save_scraped(
            article_id=article_id, url=url, title=title,
            author="", full_html="", full_text="", images=[],
        )
        return False

    data = extract_with_retry(article_id, url, title)
    word_count = data.get("word_count", 0)

    if word_count == 0:
        return False

    article_save_scraped(
        article_id=article_id,
        url=url,
        title=title[:120],
        author=data.get("author", ""),
        full_html=data.get("html", ""),
        full_text=data.get("text", ""),
        images=data.get("images", []),
    )

    images = data.get("images", [])
    if images:
        db = get_db()
        db.execute(
            "UPDATE articles SET image_url = ? WHERE id = ? AND (image_url IS NULL OR image_url = '')",
            (images[0]["src"], article_id),
        )
        db.commit()
        db.close()

    return True


def run_layer3(min_sources: int = 3) -> dict:
    """
    Process all DEVELOPING arcs:
    1. Map arc → articles via entity spine
    2. Fetch unscraped articles in arc
    3. Advance arc to FETCH_READY when MIN_FULL_TEXT articles available

    Returns summary dict.
    """
    now   = datetime.now(WIB)
    today = now.strftime("%Y-%m-%d")
    print(f"Layer 3 — Arc Maturation ({now.strftime('%Y-%m-%d %H:%M WIB')})")

    arcs = get_developing_arcs(min_sources=min_sources)
    print(f"  DEVELOPING arcs: {len(arcs)}")

    total_fetched    = 0
    total_fetch_fail = 0
    arcs_ready       = 0
    arcs_processed   = 0

    for arc in arcs:
        arc_id = arc["id"]
        spine  = arc["entity_spine"]

        # Step 1 — map arc → articles
        article_ids = _find_arc_article_ids(arc_id, spine)
        if not article_ids:
            continue

        # Load article metadata for unscraped check
        db = get_db()
        art_rows = db.execute(
            f"""SELECT a.id, a.url, a.source, a.title,
                       COALESCE(LENGTH(s.full_text), 0) as text_len,
                       s.article_id IS NOT NULL as is_scraped
                FROM articles a
                LEFT JOIN scraped_articles s ON s.article_id = a.id
                WHERE a.id IN ({','.join('?' * len(article_ids))})""",
            article_ids,
        ).fetchall()
        db.close()

        fetched_count = 0
        for art in art_rows:
            has_text = art["is_scraped"] and art["text_len"] >= 600  # ~150 words

            if has_text:
                upsert_arc_article(arc_id, art["id"], "FETCHED")
                fetched_count += 1
            elif not art["is_scraped"]:
                # On-demand fetch
                ok = _fetch_article(art["id"], art["url"], art["title"], art["source"])
                if ok:
                    upsert_arc_article(arc_id, art["id"], "FETCHED")
                    fetched_count += 1
                    total_fetched += 1
                else:
                    upsert_arc_article(arc_id, art["id"], "FAILED")
                    total_fetch_fail += 1
                time.sleep(FETCH_DELAY)
            else:
                # Scraped but thin (< 150 words)
                upsert_arc_article(arc_id, art["id"], "PENDING")

        arcs_processed += 1

        # Step 3 — advance lifecycle
        if fetched_count >= MIN_FULL_TEXT:
            advance_arc_status(arc_id, "FETCH_READY", today)
            arcs_ready += 1
            print(f"  → FETCH_READY: {spine} ({fetched_count} articles, {arc['source_count']} sources)")

    print(f"  Arcs processed: {arcs_processed}")
    print(f"  On-demand fetches: {total_fetched} ok / {total_fetch_fail} failed")
    print(f"  Arcs advanced to FETCH_READY: {arcs_ready}")

    return {
        "arcs_processed": arcs_processed,
        "fetched":        total_fetched,
        "fetch_failed":   total_fetch_fail,
        "fetch_ready":    arcs_ready,
    }


if __name__ == "__main__":
    run_layer3()
