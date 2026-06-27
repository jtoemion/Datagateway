"""
Datagateway — Hermes Writer (CODE)
Graph-aware analytical article generation with review gate.

Uses Anthropic Haiku if available, otherwise opencode-free fallback.
Review gate: CONFIRMED/REPORTED → published; SINGLE_SOURCE_AMPLIFIED/CONTESTED → pending_review.
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

HERMES_DIR = REPO_ROOT / "hermes"
WIB = timezone(timedelta(hours=7))

# ── Prompt template (8-block structure from DR-0007) ──────────────────────

SYSTEM_PROMPT = """You are Hermes, an analytical OSINT writer for Datagateway. Your role:
- Write concise, factual, source-aware analytical articles (200-500 words)
- Always cite sources and note confidence levels
- Distinguish between CONFIRMED facts, REPORTED claims, and EMERGING patterns
- Never assert causal relationships from co-occurrence alone (nPMI warning)
- Use hedged language for EMERGING/SINGLE_SOURCE_AMPLIFIED; state facts directly for CONFIRMED
- Output valid Markdown with no frontmatter"""


def build_prompt(ctx: dict) -> str:
    """Build the 8-block writer prompt from a WriterContext dict."""
    confidence = ctx["confidence"]
    articles = ctx.get("articles", [])
    entity_brief = ctx.get("entity_brief", "")
    lineage = ctx.get("lineage_context", "")
    eff_src = ctx.get("effective_sources", 0)
    src_count = ctx.get("source_count", 0)
    is_contested = ctx.get("is_contested", False)

    # Block 1: Signal metadata
    block_signal = (
        f"SIGNAL: {ctx['signal_id']}\n"
        f"Confidence: {confidence} (sources={src_count}, effective={eff_src})\n"
        f"Contested: {'Yes' if is_contested else 'No'}"
    )

    # Block 2: Lineage
    block_lineage = f"LINEAGE: {lineage}" if lineage else "LINEAGE: New story"

    # Block 3: Entity briefs
    block_entities = entity_brief or "No entities detected."

    # Block 4: Article list
    article_blocks = []
    for a in articles[:5]:
        title = a.get("title", "?")
        source = a.get("source", "?")
        date = (a.get("date") or "")[:10]
        lang = a.get("lang", "id")
        text = (a.get("full_text") or "")[:1500]
        article_blocks.append(
            f"## Article: {title}\n"
            f"Source: {source} ({date}) [{lang}]\n"
            f"---\n{text}\n---"
        )

    block_articles = "\n\n".join(article_blocks)

    # Block 5: Gate awareness
    block_gates = (
        "WRITING RULES:\n"
        "- nPMI < 0.30: Do NOT assert a relationship between entities\n"
        "- SINGLE_SOURCE_AMPLIFIED: State 'This report originates from a single source' explicitly\n"
        "- CONFIRMED: Can state facts directly with source attribution\n"
        "- CONTESTED: Present both claims neutrally; note the discrepancy\n"
        "- EMERGING: Use hedged language (suggests, indicates, appears)\n"
        "- No causal claims from co-occurrence alone\n"
        "- Coin analysis/phrasing is permissible"
    )

    # Block 6: Output instruction
    block_output = (
        "Write a concise analytical brief (200-400 words) covering:\n"
        "1. What happened (key facts)\n"
        "2. Why it matters (significance)\n"
        "3. What's uncertain (gaps, contradictions)\n"
        "4. What to watch (developing angles)\n\n"
        "Format: Markdown with ## section headers. "
        "Include a one-line summary at the top in **bold**."
    )

    return f"""# Hermes Writer — Signal Brief

{block_signal}

{block_lineage}

## Entity Context

{block_entities}

## Source Articles

{block_articles}

## {block_gates}

## {block_output}"""


def write(signal_row: dict) -> dict | None:
    """Write a Hermes analytical article for a signal.

    Args:
        signal_row: dict from signals table

    Returns:
        dict with {filepath, lineage_id, publish_state} or None on failure.
    """
    from scripts.signal.brief import build_brief

    ctx = build_brief(signal_row)
    prompt = build_prompt(ctx)

    # Determine publish state by confidence
    confidence = ctx["confidence"]
    if confidence in ("CONFIRMED", "REPORTED"):
        publish_state = "published"
    elif confidence == "EMERGING" and ctx["effective_sources"] >= 2:
        publish_state = "published"
    else:
        publish_state = "pending_review"  # SINGLE_SOURCE_AMPLIFIED, CONTESTED, low EMERGING

    # Generate article content
    content = _generate(prompt, confidence)

    if not content:
        return None

    # Write to file
    today = datetime.now(WIB).strftime("%Y-%m-%d")
    lineage_id = ctx.get("lineage_id", f"ln-{today}-unknown")

    # Sanitize lineage_id for filename
    safe_lineage = lineage_id.replace(":", "-").replace("/", "-")
    dest_dir = HERMES_DIR / today
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Find a good title from the generated content
    title_line = content.strip().split("\n")[0].strip("# ").strip("*").strip()
    slug = title_line.lower()[:50].replace(" ", "-").replace(".", "") or f"hermes-{lineage_id}"
    slug = "".join(c for c in slug if c.isalnum() or c in "-_")

    fname = f"{safe_lineage}_{slug}.md"
    fpath = dest_dir / fname

    # Check for existing (UPSERT)
    existing_content = ""
    if fpath.exists():
        existing_content = fpath.read_text(encoding="utf-8")

    full_content = (
        f"---\n"
        f"hermes_id: {ctx['signal_id']}\n"
        f"lineage_id: {lineage_id}\n"
        f"confidence: {confidence}\n"
        f"publish_state: {publish_state}\n"
        f"sources: {ctx['source_count']}\n"
        f"created_at: {datetime.now(WIB).isoformat()}\n"
        f"---\n\n"
        f"{content}\n\n"
        f"---\n\n"
        f"*Hermes \u00b7 Datagateway OSINT \u00b7 Confidence: {confidence}*"
    )

    if existing_content != full_content:
        fpath.write_text(full_content, encoding="utf-8")
        wrote = True
    else:
        wrote = False

    return {
        "filepath": str(fpath.relative_to(REPO_ROOT)),
        "lineage_id": lineage_id,
        "publish_state": publish_state,
        "wrote": wrote,
    }


def _generate(prompt: str, confidence: str) -> str | None:
    """Generate article content using available LLM.

    Tries Anthropic Haiku first, falls back to opencode-free.
    """
    # Try Anthropic
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return _generate_anthropic(prompt)
        except Exception as e:
            print(f"  [WARN] Anthropic failed: {e} — trying fallback")
            pass

    # Fallback: return a structured template
    return _generate_fallback(prompt, confidence)


def _generate_anthropic(prompt: str) -> str:
    """Generate using Anthropic Haiku 4.5."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    except ImportError:
        raise Exception("anthropic package not installed")


def _generate_fallback(prompt: str, confidence: str) -> str:
    """Generate structured analytical brief without an LLM call.

    Produces a template-based article using the signal data embedded in the prompt.
    This is the no-API-key fallback.
    """
    # Extract key info from the prompt
    lines = prompt.split("\n")
    title = "Analytical Brief"
    sources_found = 0
    entity_lines = []

    for i, line in enumerate(lines):
        if line.startswith("Title:"):
            title = line.replace("Title:", "").strip()
        if line.startswith("Source:"):
            sources_found += 1
        if "(PERSON)" in line or "(ORG)" in line or "(PLACE)" in line:
            entity_lines.append(line)

    confidence_label = {
        "CONFIRMED": "Verified across multiple independent sources",
        "REPORTED": "Reported by at least one original source",
        "EMERGING": "Initial reports — corroboration pending",
        "SINGLE_SOURCE_AMPLIFIED": "Originates from a single source, amplified by reprints",
        "CONTESTED": "Conflicting claims from different sources",
    }.get(confidence, confidence)

    entity_section = ""
    if entity_lines:
        entity_section = "\n".join(f"- {e}" for e in entity_lines[:3])

    return (
        f"**{title}**\n\n"
        f"**Assessment:** {confidence} — {confidence_label}\n\n"
        f"## Key Findings\n\n"
        f"Based on analysis of available sources, "
        f"this story carries a **{confidence}** confidence assessment "
        f"with an estimated **{sources_found}** source contributions.\n\n"
        + (f"## Key Entities\n\n{entity_section}\n\n" if entity_section else "")
        + "## What to Watch\n\n"
        "- Monitor for additional reporting from independent sources\n"
        "- Track entity co-occurrence patterns for new connections\n"
        "- Check for contradictory numeric claims in follow-up coverage\n\n"
        + f"*This brief was generated automatically. "
        f"Confidence reflects source provenance and cross-referencing.*"
    )
