"""
Datagateway — Provenance Detection (CODE)
Wire-dateline extraction, MinHash-LSH near-dup detection,
union-find provenance grouping, originator identification.
"""

import hashlib
import json
import re
from pathlib import Path
from datetime import datetime, timezone, timedelta

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
WIB = timezone(timedelta(hours=7))

# Wire agencies whose byline + dateline indicate original reporting
WIRE_AGENCIES = [
    "Reuters", "AP", "AFP", "Associated Press", "Agence France-Presse",
    "Antara", "Kyodo", "Xinhua", "DPA", "EFE", "PA Media",
]

MINHASH_PERM = 128  # Number of permutations for MinHash


def detect_wire_origin(url: str, source: str, full_text: str) -> str:
    """Detect if an article originates from a wire agency.

    Returns the wire agency name, or empty string if it appears original.
    """
    text_lower = full_text.lower()
    for agency in WIRE_AGENCIES:
        if agency.lower() in text_lower[:500]:  # Check first 500 chars
            return agency
    # Check source name
    for agency in WIRE_AGENCIES:
        if agency.lower() in source.lower():
            return agency
    return ""


def extract_dateline(full_text: str) -> str:
    """Extract dateline location from article text.

    Common patterns: 'JAKARTA, CNN Indonesia —' or 'BEIJING, Reuters —'
    Returns the location or empty string.
    """
    m = re.search(
        r'^([A-Z][A-Z\s]+)[,\s—–-]+', full_text.strip(), re.MULTILINE
    )
    if m:
        return m.group(1).strip()
    return ""


def compute_minhash(text: str) -> str:
    """Compute MinHash signature and return as JSON list of ints."""
    from datasketch import MinHash
    mh = MinHash(num_perm=MINHASH_PERM)
    for token in text.lower().split():
        mh.update(token.encode("utf-8"))
    return json.dumps(mh.digest().tolist())


def jaccard_similarity(sig_a: str, sig_b: str) -> float:
    """Compute Jaccard similarity between two MinHash signatures."""
    from datasketch import MinHash
    a_vals = json.loads(sig_a)
    b_vals = json.loads(sig_b)
    mh_a = MinHash(num_perm=MINHASH_PERM, hashvalues=a_vals)
    mh_b = MinHash(num_perm=MINHASH_PERM, hashvalues=b_vals)
    return mh_a.jaccard(mh_b)


def find_provenance_groups() -> int:
    """Find provenance groups among articles.

    Returns number of groups found.
    Uses MinHash-LSH to find candidates, then exact-Jaccard to verify.
    """
    from scripts.database import get_db

    db = get_db()

    # Get all articles with scraped content that don't have a provenance group
    articles = db.execute(
        """SELECT a.id, a.source, a.url, a.title,
                  s.full_text, s.full_html,
                  a.minhash_sig, a.wire_origin
           FROM articles a
           LEFT JOIN scraped_articles s ON a.id = s.article_id
           WHERE s.full_text IS NOT NULL AND s.full_text != ''
           ORDER BY a.date DESC
           LIMIT 500"""
    ).fetchall()

    if not articles:
        db.close()
        return 0

    # Compute MinHash for articles that lack one
    from datasketch import MinHashLSH
    lsh = MinHashLSH(threshold=0.6, num_perm=MINHASH_PERM)

    from datasketch import MinHash as _MH

    sigs = {}      # aid → raw hashvalues list (for Jaccard comparison)
    minhashes = {} # aid → MinHash object (for LSH operations)

    for r in articles:
        aid = r["id"]
        sig_s = r["minhash_sig"]
        if not sig_s:
            sig_s = compute_minhash(r["full_text"] or r["full_html"] or "")
            db.execute(
                "UPDATE articles SET minhash_sig = ? WHERE id = ?",
                (sig_s, aid),
            )
        hashvals = json.loads(sig_s)
        sigs[aid] = hashvals
        mh = _MH(num_perm=MINHASH_PERM, hashvalues=hashvals)
        minhashes[aid] = mh
        lsh.insert(aid, mh)

    # Find near-duplicates using LSH + exact Jaccard verify
    groups = {}
    group_id = 0
    assigned = set()

    for aid, mh in minhashes.items():
        if aid in assigned:
            continue
        candidates = lsh.query(mh)
        if len(candidates) <= 1:
            # Singleton — not part of a group, but check wire origin
            r_row = next((r for r in articles if r["id"] == aid), None)
            wire = detect_wire_origin(
                r_row["url"] if r_row else "",
                r_row["source"] if r_row else "",
                r_row["full_text"] or "" if r_row else "",
            )
            if wire:
                db.execute(
                    "UPDATE articles SET wire_origin = ? WHERE id = ?",
                    (wire, aid),
                )
            continue

        # Verify each candidate with exact Jaccard
        verified = [aid]
        for cand in candidates:
            if cand == aid or cand in assigned:
                continue
            if sigs.get(cand) and jaccard_similarity(
                json.dumps(sigs[aid]), json.dumps(sigs[cand])
            ) >= 0.7:
                verified.append(cand)

        if len(verified) >= 2:
            group_id += 1
            gid = f"prov-{group_id:04d}"
            # First article in verified list is originator
            originator = verified[0]
            for vid in verified:
                db.execute(
                    """UPDATE articles SET
                       provenance_group = ?,
                       wire_origin = COALESCE(wire_origin, ?),
                       is_originator = CASE WHEN id = ? THEN 1 ELSE 0 END
                       WHERE id = ?""",
                    (gid, "wire-group", originator, vid),
                )
                assigned.add(vid)

            db.execute(
                """INSERT OR REPLACE INTO provenance_groups
                   (id, originator_article_id, match_type, group_size, created_at)
                   VALUES (?, ?, 'near-dup', ?, datetime('now'))""",
                (gid, originator, len(verified)),
            )

    db.commit()
    db.close()
    return group_id
