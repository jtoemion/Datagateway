#!/usr/bin/env bash
# Datagateway — Run pipeline: fetch → build dashboard
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== Datagateway Pipeline ==="
echo ""

echo "[1/2] Fetch news..."
python3 scripts/fetch-news.py

echo ""
echo "[2/2] Build dashboard..."
python3 scripts/build-dashboard.py

echo ""
echo "=== Done ==="
