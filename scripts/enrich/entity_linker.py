"""
Datagateway — Entity Linker (CODE)
Resolve raw entities → canonical entities in the database.
Handles alias resolution, first-appearance guard, co-occurrence tracking.
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from rapidfuzz import fuzz

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

WIB = timezone(timedelta(hours=7))

# Minimum similarity for fuzzy alias matching (DR-0012 §6 guard)
ALIAS_SIMILARITY = 88

# Load synonym_map for seed aliases
_synonym_map: dict[str, list[str]] = {}


def _load_synonyms():
    global _synonym_map
    if _synonym_map:
        return
    path = REPO_ROOT / "data" / "synonym_map.json"
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                _synonym_map = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass


def _canonical_from_synonym(surface: str) -> str | None:
    """Check if surface is an alias in the synonym map; return canonical key if found."""
    _load_synonyms()
    surface_lower = surface.lower()
    for canonical, aliases in _synonym_map.items():
        if canonical.lower() == surface_lower:
            return canonical
        for alias in aliases:
            if alias.lower() == surface_lower:
                return canonical
    return None


def _make_entity_id(canonical: str) -> str:
    import hashlib
    return "ent-" + hashlib.md5(canonical.lower().encode()).hexdigest()[:12]


def link_entities(
    raw_entities: list[dict],
    source: str = "",
    article_date: str = "",
) -> list[dict]:
    """
    Resolve raw entities against the entities table.

    Returns list of LinkedEntity dicts:
        {entity_id, canonical, type, surface, is_new, aliases}
    """
    from scripts.database import get_db

    db = get_db()
    today = datetime.now(WIB).strftime("%Y-%m-%d")
    date_tag = article_date[:10] if article_date else today
    linked: list[dict] = []
    seen_canonicals: set[str] = set()

    for raw in raw_entities:
        surface = raw["surface"]
        etype = raw["type"]
        entity_id = raw["entity_id"]

        # 1. Check synonym map for canonical override
        synonym_canonical = _canonical_from_synonym(surface)
        if synonym_canonical:
            canonical = synonym_canonical
        else:
            canonical = surface

        canonical_lower = canonical.lower().strip()

        # 2. Check DB for existing entity (exact canonical)
        existing = db.execute(
            "SELECT id, canonical, aliases_json, article_count FROM entities WHERE canonical = ?",
            (canonical,),
        ).fetchone()

        if existing:
            eid = existing["id"]
            # Update last_seen + article_count
            db.execute(
                "UPDATE entities SET last_seen = ?, article_count = article_count + 1 WHERE id = ?",
                (today, eid),
            )
            # Add new alias if surface differs from canonical and not already in aliases
            if canonical.lower() != surface.lower():
                aliases = json.loads(existing["aliases_json"] or "[]")
                if surface not in aliases:
                    aliases.append(surface)
                    db.execute(
                        "UPDATE entities SET aliases_json = ? WHERE id = ?",
                        (json.dumps(aliases, ensure_ascii=False), eid),
                    )

            is_new = False
        else:
            # 3. Fuzzy alias check (DR-0012 §6 guard) — prevent noise entities
            fuzzy_match = db.execute(
                "SELECT id, canonical, type FROM entities WHERE type = ?",
                (etype,),
            ).fetchall()
            matched = False
            for row in fuzzy_match:
                score = fuzz.ratio(canonical_lower, row["canonical"].lower())
                if score >= ALIAS_SIMILARITY:
                    # This is actually the same entity — merge
                    eid = row["id"]
                    db.execute(
                        "UPDATE entities SET last_seen = ?, article_count = article_count + 1 WHERE id = ?",
                        (today, eid),
                    )
                    matched = True
                    is_new = False
                    canonical = row["canonical"]
                    break

            if not matched:
                # 4. Create new entity
                eid = entity_id or _make_entity_id(canonical)
                aliases = [surface] if canonical.lower() != surface.lower() else []
                try:
                    db.execute(
                        """INSERT INTO entities (id, canonical, type, aliases_json, first_seen, last_seen, article_count)
                           VALUES (?, ?, ?, ?, ?, ?, 1)""",
                        (eid, canonical, etype, json.dumps(aliases, ensure_ascii=False), today, today),
                    )
                    is_new = True
                except Exception:
                    # Race condition — entity was just created by another process
                    db.rollback()
                    existing = db.execute(
                        "SELECT id FROM entities WHERE canonical = ?", (canonical,)
                    ).fetchone()
                    if existing:
                        eid = existing["id"]
                        db.execute(
                            "UPDATE entities SET last_seen = ?, article_count = article_count + 1 WHERE id = ?",
                            (today, eid),
                        )
                        is_new = False
                    else:
                        raise

        # Track for co-occurrence update
        if canonical_lower not in seen_canonicals:
            seen_canonicals.add(canonical_lower)
            linked.append({
                "entity_id": eid,
                "canonical": canonical,
                "type": etype,
                "surface": surface,
                "is_new": is_new,
            })

    # 5. Update co-occurrence for all pairs in this article
    for i in range(len(linked)):
        for j in range(i + 1, len(linked)):
            a_id, b_id = linked[i]["entity_id"], linked[j]["entity_id"]
            if a_id < b_id:
                e1, e2 = a_id, b_id
            else:
                e1, e2 = b_id, a_id
            db.execute(
                """INSERT INTO entity_cooccurrence (entity_a, entity_b, co_count, last_seen, date)
                   VALUES (?, ?, 1, ?, ?)
                   ON CONFLICT(entity_a, entity_b) DO UPDATE SET
                       co_count = co_count + 1,
                       last_seen = ?,
                       date = ?""",
                (e1, e2, today, date_tag, today, date_tag),
            )

    db.commit()
    db.close()
    return linked


def get_entity_briefs(article_id: str, max_entities: int = 8) -> str:
    """
    Build compressed entity brief section for the Hermes writer.
    Includes ⚡ FIRST APPEARANCE and ⚠ NEW CO-OCCURRENCE flags.
    """
    from scripts.database import get_db
    db = get_db()

    today = datetime.now(WIB).strftime("%Y-%m-%d")

    rows = db.execute(
        """SELECT e.id, e.canonical, e.type, e.article_count, e.first_seen, e.last_seen,
                  ae.mention_count
           FROM article_entities ae
           JOIN entities e ON ae.entity_id = e.id
           WHERE ae.article_id = ?
           ORDER BY ae.mention_count DESC
           LIMIT ?""",
        (article_id, max_entities),
    ).fetchall()

    if not rows:
        db.close()
        return ""

    lines = ["[ENTITY BRIEF]"]
    for r in rows:
        first_seen = r["first_seen"]
        is_new_today = first_seen == today
        flag = " — ⚡ FIRST APPEARANCE TODAY" if is_new_today else ""
        lines.append(
            f"{r['canonical']} ({r['type']}) — {r['article_count']} mentions"
            f"{flag}"
        )

        # Top co-occurrences
        co_rows = db.execute(
            """SELECT e.canonical, c.co_count
               FROM entity_cooccurrence c
               JOIN entities e ON (e.id = CASE WHEN c.entity_a = ? THEN c.entity_b ELSE c.entity_a END)
               WHERE c.entity_a = ? OR c.entity_b = ?
               ORDER BY c.co_count DESC
               LIMIT 3""",
            (r["id"], r["id"], r["id"]),
        ).fetchall()
        if co_rows:
            co_parts = [f"{cr['canonical']} ({cr['co_count']}x)" for cr in co_rows]
            lines.append(f"  Co-appears: {', '.join(co_parts)}")

    db.close()
    return "\n".join(lines)
