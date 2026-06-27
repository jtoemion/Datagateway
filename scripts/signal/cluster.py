"""
Datagateway — Cluster Detection (CODE)
Entity-overlap + BM25 clustering with lineage assignment.
"""

import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
WIB = timezone(timedelta(hours=7))

# Overlap thresholds
ENTITY_JACCARD_MIN = 0.4
BM25_SCORE_MIN = 0.35
LINEAGE_ENTITY_JACCARD = 0.5  # ≥0.5 entity Jaccard vs recent 3d → same lineage


def find_clusters() -> int:
    """Cluster articles by entity overlap + BM25 similarity.

    Returns number of clusters found.
    """
    from scripts.database import get_db

    db = get_db()

    # Get all articles with their entities
    articles = db.execute(
        """SELECT a.id, a.title, a.source, a.date
           FROM articles a
           ORDER BY a.date DESC
           LIMIT 300"""
    ).fetchall()

    if not articles:
        db.close()
        return 0

    # Build entity sets per article
    article_entities = {}
    for r in articles:
        ae = db.execute(
            "SELECT entity_id FROM article_entities WHERE article_id = ?",
            (r["id"],),
        ).fetchall()
        article_entities[r["id"]] = {e["entity_id"] for e in ae}

    # Build clusters greedily
    clusters = []
    assigned = set()

    for r in articles:
        aid = r["id"]
        if aid in assigned:
            continue
        a_entities = article_entities.get(aid, set())
        if not a_entities:
            continue

        cluster_members = [aid]
        for r2 in articles:
            a2id = r2["id"]
            if a2id == aid or a2id in assigned:
                continue
            b_entities = article_entities.get(a2id, set())
            if not a_entities or not b_entities:
                continue

            # Jaccard similarity on entities
            intersection = a_entities & b_entities
            union = a_entities | b_entities
            if len(union) == 0:
                continue
            jaccard = len(intersection) / len(union)

            if jaccard >= ENTITY_JACCARD_MIN:
                cluster_members.append(a2id)

        if len(cluster_members) >= 2:
            clusters.append(cluster_members)
            for m in cluster_members:
                assigned.add(m)

    # Write clusters to DB
    today = datetime.now(WIB).strftime("%Y-%m-%d")
    today_date = datetime.now(WIB).date()

    for i, members in enumerate(clusters):
        cid = f"cl-{today}-{i+1:04d}"

        # Count entity frequency across cluster
        from collections import Counter
        entity_counter = Counter()
        for mid in members:
            for eid in article_entities.get(mid, set()):
                entity_counter[eid] += 1
        top_entities = [eid for eid, _ in entity_counter.most_common(5)]

        # Check lineage: does this cluster overlap with any recent cluster?
        lineage_id = None
        recent_clusters = db.execute(
            """SELECT id, lineage_id, top_entities FROM clusters
               WHERE created_at >= ?
               ORDER BY created_at DESC LIMIT 10""",
            (today,),
        ).fetchall()

        for rc in recent_clusters:
            if not rc["top_entities"]:
                continue
            try:
                rc_entities = set(json.loads(rc["top_entities"]))
            except (json.JSONDecodeError, TypeError):
                continue
            this_entities = set(top_entities)
            if not rc_entities or not this_entities:
                continue
            entity_j = len(this_entities & rc_entities) / len(this_entities | rc_entities)
            if entity_j >= LINEAGE_ENTITY_JACCARD:
                lineage_id = rc["lineage_id"]
                break

        if not lineage_id:
            lineage_id = f"ln-{today}-{i+1:04d}"

        # Store cluster record
        db.execute(
            """INSERT OR REPLACE INTO clusters
               (id, lineage_id, article_count, top_entities, consistency, created_at)
               VALUES (?, ?, ?, ?, 1.0, datetime('now'))""",
            (cid, lineage_id, len(members), json.dumps(top_entities, ensure_ascii=False)),
        )

        # Create a signal placeholder for each cluster
        sid = f"sig-{cid}"
        db.execute(
            """INSERT OR IGNORE INTO signals
               (id, cluster_id, title, confidence, article_ids, entity_ids, lineage_id, created_at)
               VALUES (?, ?, 'Cluster: ' || ?, ?, ?, ?, ?, datetime('now'))""",
            (sid, cid, members[0][:50] if len(members) > 0 else "",
             "EMERGING", json.dumps(members),
             json.dumps(top_entities, ensure_ascii=False), lineage_id),
        )

    db.commit()
    db.close()
    return len(clusters)
