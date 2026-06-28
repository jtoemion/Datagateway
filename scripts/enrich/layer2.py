"""
Datagateway — Layer 2 Gateway (GATEWAY)
Entity graph: compute nPMI, detect arc candidates, report window signals.

Runs after entity enrichment. Inputs: entities + entity_cooccurrence.
Outputs: nPMI scores persisted to DB + arc candidates for Layer 3.
"""

import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.signal.pmi import compute_npmi
from scripts.database import (
    get_db,
    save_npmi_scores,
    get_entities_window,
    get_cooccurrences_window,
    upsert_arc,
)

WIB = timezone(timedelta(hours=7))

WINDOW_HOURS      = 24
ARC_MIN_SOURCES   = 2   # sources needed to register an arc (EMERGING)
ARC_DEV_SOURCES   = 3   # sources needed to advance to DEVELOPING
NPMI_GATE         = 0.30


def run_layer2() -> dict:
    """
    1. Compute and persist nPMI scores.
    2. Find entity pairs active in the last 24h with ≥ ARC_MIN_SOURCES.
    3. Upsert arc records for qualifying pairs.

    Returns summary dict for pipeline logging.
    """
    now = datetime.now(WIB)
    today = now.strftime("%Y-%m-%d")
    print(f"Layer 2 — Entity Graph ({now.strftime('%Y-%m-%d %H:%M WIB')})")

    # ── 1. nPMI ──────────────────────────────────────────────────────────────
    db = get_db()
    total_articles = db.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    db.close()

    npmi_scores = compute_npmi(total_articles=max(total_articles, 1))
    save_npmi_scores(npmi_scores)
    print(f"  nPMI: {len(npmi_scores)//2} pairs scored")

    # ── 2. Window entities — what's active today ──────────────────────────────
    window_entities = get_entities_window(hours=WINDOW_HOURS)
    print(f"  Active entities (24h, ≥2 sources): {len(window_entities)}")

    if window_entities:
        print("  Top entities:")
        for e in window_entities[:8]:
            srcs = e["sources"] or ""
            print(f"    {e['canonical']} ({e['type']}) — {e['source_count']} sources: {srcs}")

    # ── 3. Arc detection — entity pairs with cross-source co-occurrence ───────
    arcs_found = 0
    ubiquity_cap = max(1, total_articles * 0.25)  # entities in >25% of articles = noise

    # Build source map: entity_id → sources set (from window)
    entity_sources: dict[str, set[str]] = {}
    db = get_db()
    cutoff = (now - timedelta(hours=WINDOW_HOURS)).strftime("%Y-%m-%d")
    rows = db.execute(
        """SELECT ae.entity_id, ae.source
           FROM article_entities ae
           WHERE ae.article_date >= ? AND ae.source != ''
           GROUP BY ae.entity_id, ae.source""",
        (cutoff,),
    ).fetchall()
    db.close()
    for r in rows:
        entity_sources.setdefault(r["entity_id"], set()).add(r["source"])

    # Load entity metadata for gates
    db = get_db()
    entity_meta: dict[str, dict] = {}
    meta_rows = db.execute(
        "SELECT id, canonical, type, article_count FROM entities"
    ).fetchall()
    db.close()
    for r in meta_rows:
        entity_meta[r["id"]] = {"canonical": r["canonical"], "type": r["type"], "count": r["article_count"]}

    # Co-occurrence pairs that qualify as arc seeds
    db = get_db()
    pair_rows = db.execute(
        """SELECT entity_a, entity_b, co_count, nPMI
           FROM entity_cooccurrence
           WHERE date >= ? AND nPMI >= ?
           ORDER BY nPMI DESC, co_count DESC""",
        (cutoff, NPMI_GATE),
    ).fetchall()
    db.close()

    for pr in pair_rows:
        a_meta = entity_meta.get(pr["entity_a"])
        b_meta = entity_meta.get(pr["entity_b"])
        if not a_meta or not b_meta:
            continue

        # Gate 1: ubiquity — skip entities appearing in >25% of all articles
        if a_meta["count"] > ubiquity_cap or b_meta["count"] > ubiquity_cap:
            continue

        # Gate 2: type diversity — arc spine must include at least one non-PLACE entity
        types = {a_meta["type"], b_meta["type"]}
        if types == {"PLACE"}:
            continue

        a_sources = entity_sources.get(pr["entity_a"], set())
        b_sources = entity_sources.get(pr["entity_b"], set())
        shared_sources = sorted(a_sources & b_sources)

        if len(shared_sources) < ARC_MIN_SOURCES:
            continue

        spine = f"{a_meta['canonical']} × {b_meta['canonical']}"
        upsert_arc(spine, shared_sources, today)
        arcs_found += 1

    print(f"  Arc records upserted: {arcs_found}")

    # ── 4. Summary of active arcs ─────────────────────────────────────────────
    db = get_db()
    arc_summary = db.execute(
        "SELECT status, COUNT(*) as cnt FROM arcs WHERE status != 'CONCLUDED' GROUP BY status"
    ).fetchall()
    db.close()
    for row in arc_summary:
        print(f"  Arcs {row['status']}: {row['cnt']}")

    return {
        "npmi_pairs": len(npmi_scores) // 2,
        "active_entities": len(window_entities),
        "arcs_upserted": arcs_found,
    }


if __name__ == "__main__":
    run_layer2()
