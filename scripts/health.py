"""
Datagateway — Run Health (CODE)
Writes last_run.json as the FINAL step of run.sh.
"""

import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
HEALTH_FILE = DATA_DIR / "last_run.json"

WIB = timezone(timedelta(hours=7))


def write_success(steps: int = 11):
    """Write a successful run marker."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": "ok",
        "completed_at": datetime.now(WIB).isoformat(),
        "completed_at_ts": datetime.now(WIB).timestamp(),
        "steps": steps,
    }
    HEALTH_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def read_status() -> dict:
    """Read last run status. Returns dict with status, completed_at, etc."""
    if not HEALTH_FILE.exists():
        return {"status": "missing", "completed_at": None}
    try:
        data = json.loads(HEALTH_FILE.read_text(encoding="utf-8"))
        return {
            "status": data.get("status", "unknown"),
            "completed_at": data.get("completed_at"),
            "completed_at_ts": data.get("completed_at_ts", 0),
            "steps": data.get("steps", 0),
        }
    except (json.JSONDecodeError, OSError):
        return {"status": "corrupt", "completed_at": None}


def is_fresh(max_hours: float = 13) -> bool:
    """Check if the last run is within max_hours (default 13)."""
    status = read_status()
    ts = status.get("completed_at_ts", 0)
    if not ts:
        return False
    from datetime import datetime, timezone
    now = datetime.now(WIB).timestamp()
    return (now - ts) < (max_hours * 3600)
