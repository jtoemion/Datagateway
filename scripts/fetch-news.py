#!/usr/bin/env python3
"""
fetch-news.py — SHIM
Delegates to sources.gateway.run() which reads config.yaml.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.sources.gateway import run

if __name__ == "__main__":
    run()
