"""
Datagateway — Web Fetcher (CODE)
OpenCode fallback — used when extractor returns < 150 words.
Currently a stub; actual OpenCode integration deferred to a later phase.

Returns:
    {"text": "", "html": "", "author": ""}
"""

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def fetch(url: str) -> dict:
    """
    Fetch article content via OpenCode as a fallback when extractor
    returns < 150 words.

    STUB: Always returns empty. Full OpenCode integration is a later phase.
    """
    return {
        "text": "",
        "html": "",
        "author": "",
    }
