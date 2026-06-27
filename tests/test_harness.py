"""Tests for Datagateway — verify test harness works."""

import pytest


def test_harness(fixture_conn):
    """Sanity: fixture DB has articles."""
    count = fixture_conn.execute("SELECT COUNT(*) as cnt FROM articles").fetchone()["cnt"]
    assert count > 0, "Fixture DB should have articles"
    assert count <= 35, "Fixture should be limited to ~30 articles"


def test_sources_table(fixture_conn):
    """Sources table exists and has data."""
    rows = fixture_conn.execute("SELECT * FROM sources").fetchall()
    assert len(rows) > 0
    for r in rows:
        assert r["name"]
        assert r["url"]


def test_schema_version(fixture_db_path):
    """Migrate runner is idempotent against fixture DB."""
    import subprocess, sys
    result = subprocess.run(
        [sys.executable, str(fixture_db_path.parent.parent.parent / "scripts" / "migrate.py")],
        capture_output=True, text=True,
        env={"PYTHONPATH": str(fixture_db_path.parent.parent.parent)},
    )
    # Should succeed with no errors (may say "Nothing to migrate")
    assert result.returncode == 0, f"migrate failed: {result.stderr}"
