#!/usr/bin/env python3
"""
build-dashboard.py — SHIM
Delegates to render.gateway; kept for backward compatibility.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.render.gateway import build_dashboard
from scripts.database import init_db, get_articles


def main():
    init_db()
    articles = get_articles(limit=500)
    path = build_dashboard(articles)
    from datetime import datetime, timezone, timedelta
    wib = timezone(timedelta(hours=7))
    print(f"Datagateway — Build Dashboard (via render.gateway)")
    print(f"  News: {len(articles)} articles")
    from scripts.database import get_football_count
    print(f"  Football: {get_football_count()} events")
    print(f"  Dashboard: {path}")


if __name__ == "__main__":
    main()
