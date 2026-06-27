"""Datagateway test fixtures."""

import pytest
import sqlite3
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
FIXTURE_DB = TESTS_DIR / "data" / "fixture.db"
REPO_ROOT = TESTS_DIR.parent


@pytest.fixture
def fixture_db_path() -> Path:
    """Path to the fixture database (pre-seeded with real data)."""
    if not FIXTURE_DB.exists():
        return _seed_fixture_db()
    return FIXTURE_DB


@pytest.fixture
def fixture_conn(fixture_db_path: Path) -> sqlite3.Connection:
    """SQLite connection to the fixture database, read-only."""
    db = sqlite3.connect(f"file:{fixture_db_path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    yield db
    db.close()


def _seed_fixture_db() -> Path:
    """Create fixture DB from the real datagateway.db (top ~30 articles)."""
    real_db = REPO_ROOT / "datagateway.db"
    if not real_db.exists():
        raise FileNotFoundError(
            f"No real DB at {real_db}. Run the pipeline first, or place a fixture.db manually."
        )

    src = sqlite3.connect(str(real_db))
    src.row_factory = sqlite3.Row

    dst = sqlite3.connect(str(FIXTURE_DB))
    dst.execute("PRAGMA journal_mode=OFF")

    # Copy schema
    src.backup(dst, pages=0)

    # Keep only ~30 articles + related data
    article_ids = [r["id"] for r in src.execute(
        "SELECT id FROM articles ORDER BY date DESC LIMIT 30"
    ).fetchall()]

    dst.execute("DELETE FROM articles WHERE id NOT IN ({})".format(
        ",".join("?" for _ in article_ids)
    ), article_ids)
    dst.execute("DELETE FROM scraped_articles WHERE article_id NOT IN ({})".format(
        ",".join("?" for _ in article_ids)
    ), article_ids)
    dst.execute("DELETE FROM article_metadata WHERE article_id NOT IN ({})".format(
        ",".join("?" for _ in article_ids)
    ), article_ids)
    dst.commit()
    src.close()
    dst.close()

    print(f"  Seeded fixture DB: {FIXTURE_DB} ({len(article_ids)} articles)")
    return FIXTURE_DB
