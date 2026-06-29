"""
Datagateway — Layer 4: Arc Synthesis (CODE)
Reads FETCH_READY arcs, synthesizes a conclusion article from their
full-text articles, writes to hermes/, marks arc CONCLUDED.

Protocol:
  - Use ONLY facts present in the provided articles
  - Attribute every claim to a source
  - Hedged language for unverified/single-source claims
  - No causal claims from entity co-occurrence alone
  - Output: Indonesian if majority sources are id, else English
"""

import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.database import (
    get_db,
    get_fetch_ready_arcs,
    get_arc_articles,
    advance_arc_status,
)

WIB        = timezone(timedelta(hours=7))
HERMES_DIR = REPO_ROOT / "hermes"
HERMES_DIR.mkdir(exist_ok=True)

MIN_ARTICLES_FOR_SYNTHESIS = 3
MAX_ARTICLE_CHARS          = 1800   # per article in prompt
MAX_ARTICLES_IN_PROMPT     = 6

EN_SOURCES = {
    "BBC News", "BBC Football", "BBC Indonesia",
    "Sky Sports Football", "The Guardian Football",
    "NY Times", "NY Times Soccer", "Fox Sports Soccer",
}

SYSTEM_PROMPT_ID = """Kamu adalah Hermes, analis intelijen berita untuk Datagateway.
Tugasmu: tulis artikel sintesis yang tajam dan faktual dari artikel-artikel yang diberikan.

ATURAN KETAT:
- Gunakan HANYA fakta yang ada dalam artikel yang disediakan. Jangan menambahkan konteks eksternal.
- Setiap klaim harus disertai atribusi sumber (mis. "Menurut Republika, ...")
- Gunakan bahasa yang terhindar untuk klaim yang hanya dari satu sumber
- Jangan buat hubungan sebab-akibat dari ko-orisinal entitas saja
- Panjang: 250-450 kata
- Format: Markdown dengan header ## """

SYSTEM_PROMPT_EN = """You are Hermes, an analytical intelligence writer for Datagateway.
Your task: write a sharp, factual synthesis article from the provided sources.

STRICT RULES:
- Use ONLY facts present in the provided articles. Add no external context.
- Attribute every claim to a source (e.g. "According to The Guardian, ...")
- Use hedged language for single-source claims
- No causal claims from entity co-occurrence alone
- Length: 250-450 words
- Format: Markdown with ## headers"""


def _slug(spine: str) -> str:
    """Convert arc spine to a safe filename slug."""
    s = spine.lower()
    s = re.sub(r"[×\s]+", "-", s)
    s = re.sub(r"[^a-z0-9\-]", "", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:80]


def _detect_lang(sources: list[str]) -> str:
    en_count = sum(1 for s in sources if s in EN_SOURCES)
    return "en" if en_count > len(sources) / 2 else "id"


def _spine_entity_ids(spine: str) -> list[str]:
    """Resolve spine entity names → entity IDs."""
    db = get_db()
    ids = []
    for name in [e.strip() for e in spine.split("×")]:
        row = db.execute("SELECT id FROM entities WHERE canonical = ?", (name,)).fetchone()
        if row:
            ids.append(row["id"])
    db.close()
    return ids


def _article_relevance(article_id: str, entity_ids: list[str]) -> int:
    """Sum of mention counts for spine entities in this article."""
    if not entity_ids:
        return 0
    db = get_db()
    placeholders = ",".join("?" * len(entity_ids))
    row = db.execute(
        f"SELECT COALESCE(SUM(mention_count), 0) as total FROM article_entities "
        f"WHERE article_id = ? AND entity_id IN ({placeholders})",
        [article_id] + entity_ids,
    ).fetchone()
    db.close()
    return row["total"] if row else 0


def _build_prompt(arc: dict, articles: list[dict], lang: str) -> str:
    spine       = arc["entity_spine"]
    source_list = arc["sources"]
    today       = datetime.now(WIB).strftime("%Y-%m-%d")

    spine_eids = _spine_entity_ids(spine)

    # Sort by entity relevance (spine entities centrality), then deduplicate by source
    scored = sorted(
        articles,
        key=lambda a: _article_relevance(a["article_id"], spine_eids),
        reverse=True,
    )
    seen_sources: set[str] = set()
    ranked = []
    for a in scored:
        if a["source"] not in seen_sources:
            ranked.append(a)
            seen_sources.add(a["source"])
        if len(ranked) >= MAX_ARTICLES_IN_PROMPT:
            break

    article_blocks = []
    for a in ranked:
        text = (a.get("full_text") or "")[:MAX_ARTICLE_CHARS].strip()
        if not text:
            # Fall back to normalized_description if full text is absent
            db = get_db()
            nd = db.execute(
                "SELECT normalized_description FROM articles WHERE id = ?",
                (a["article_id"],),
            ).fetchone()
            db.close()
            text = (nd["normalized_description"] if nd else "") or ""
        if not text:
            continue
        date_tag = (a.get("date") or today)[:10]
        article_blocks.append(
            f"### {a['source']} ({date_tag})\n"
            f"**Judul / Title:** {a.get('title', '')}\n\n"
            f"{text}"
        )

    articles_section = "\n\n---\n\n".join(article_blocks)

    if lang == "id":
        return f"""# Permintaan Sintesis Arc

**Topik Arc:** {spine}
**Sumber yang melaporkan:** {', '.join(source_list)}
**Jumlah artikel:** {len(ranked)}
**Tanggal:** {today}

## Artikel Sumber

{articles_section}

## Instruksi

Tulis artikel sintesis Markdown (250-450 kata) dengan struktur:
1. **Ringkasan** — satu paragraf apa yang terjadi
2. ## Apa yang Terjadi — fakta-fakta kunci dengan atribusi sumber
3. ## Mengapa Penting — signifikansi, dampak potensial
4. ## Yang Belum Jelas — kesenjangan informasi, klaim yang belum terkonfirmasi
5. ## Yang Perlu Dipantau — sudut yang sedang berkembang

Mulai dengan satu kalimat bold sebagai ringkasan di baris pertama."""
    else:
        return f"""# Arc Synthesis Request

**Arc topic:** {spine}
**Reporting sources:** {', '.join(source_list)}
**Article count:** {len(ranked)}
**Date:** {today}

## Source Articles

{articles_section}

## Instructions

Write a Markdown synthesis article (250-450 words) structured as:
1. **Summary** — one paragraph stating what happened
2. ## What Happened — key facts with source attribution
3. ## Why It Matters — significance and potential impact
4. ## What's Unclear — information gaps, unverified claims
5. ## What to Watch — developing angles

Open with a single bold sentence as the top-line summary."""


def _generate(prompt: str, lang: str) -> str | None:
    system = SYSTEM_PROMPT_ID if lang == "id" else SYSTEM_PROMPT_EN
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        print(f"    [layer4] AI error: {e}")
        return None


def _write_hermes_article(arc: dict, content: str, lang: str) -> str:
    """Write synthesis to hermes/ and return the relative filepath."""
    spine = arc["entity_spine"]
    today = datetime.now(WIB).strftime("%Y-%m-%d")
    slug  = _slug(spine)
    fname = f"arc-{today}-{slug}.md"
    fpath = HERMES_DIR / fname

    sources_yaml = json.dumps(arc["sources"], ensure_ascii=False)
    frontmatter = (
        f"---\n"
        f"arc: \"{spine}\"\n"
        f"sources: {sources_yaml}\n"
        f"source_count: {arc['source_count']}\n"
        f"status: CONCLUDED\n"
        f"lang: {lang}\n"
        f"date: {today}\n"
        f"generator: hermes-layer4\n"
        f"---\n\n"
    )

    fpath.write_text(frontmatter + content + "\n", encoding="utf-8")
    return str(fpath.relative_to(REPO_ROOT))


def run_layer4(max_arcs: int = 10) -> dict:
    """
    Synthesize FETCH_READY arcs into Hermes conclusion articles.
    Returns summary dict.
    """
    now   = datetime.now(WIB)
    today = now.strftime("%Y-%m-%d")
    print(f"Layer 4 — Arc Synthesis ({now.strftime('%Y-%m-%d %H:%M WIB')})")

    arcs = get_fetch_ready_arcs()
    print(f"  FETCH_READY arcs: {len(arcs)}")

    if not arcs:
        return {"arcs_attempted": 0, "written": 0, "skipped": 0}

    written  = 0
    skipped  = 0

    for arc in arcs[:max_arcs]:
        arc_id = arc["id"]
        spine  = arc["entity_spine"]

        articles = get_arc_articles(arc_id)
        full_text_articles = [
            a for a in articles
            if a.get("fetch_status") == "FETCHED" and a.get("full_text")
        ]

        if len(full_text_articles) < MIN_ARTICLES_FOR_SYNTHESIS:
            skipped += 1
            continue

        # Check if we already wrote a conclusion for this arc today
        db = get_db()
        existing = db.execute(
            "SELECT conclusion_id FROM arcs WHERE id = ? AND conclusion_id IS NOT NULL",
            (arc_id,),
        ).fetchone()
        db.close()
        if existing:
            skipped += 1
            continue

        lang   = _detect_lang(arc["sources"])
        prompt = _build_prompt(arc, full_text_articles, lang)
        content = _generate(prompt, lang)

        if not content:
            skipped += 1
            continue

        filepath = _write_hermes_article(arc, content, lang)

        # Mark arc CONCLUDED and store filepath as conclusion_id
        db = get_db()
        db.execute(
            "UPDATE arcs SET status = 'CONCLUDED', conclusion_id = ?, last_updated = ? WHERE id = ?",
            (filepath, today, arc_id),
        )
        db.commit()
        db.close()

        written += 1
        print(f"  → wrote: {filepath}")
        print(f"    [{lang.upper()}] {spine} — {len(full_text_articles)} articles, {arc['source_count']} sources")

    print(f"  Written: {written} | Skipped: {skipped}")
    return {"arcs_attempted": min(len(arcs), max_arcs), "written": written, "skipped": skipped}


if __name__ == "__main__":
    run_layer4()
