"""
Datagateway — Football Fetcher (CODE)
Migrated from fetch-football.py unchanged in behavior.
TheRundown API → football_events + football_odds.
"""

import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import requests

from scripts.database import (
    init_db,
    cache_get,
    cache_set,
    football_upsert_event,
    football_upsert_odds,
    get_football_count,
)

WIB = timezone(timedelta(hours=7))
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# TheRundown API key — env var → .therundown_key file
API_KEY = os.environ.get("THEDERUNDOWN_KEY", "")
if not API_KEY:
    key_file = REPO_ROOT / ".therundown_key"
    if key_file.exists():
        API_KEY = key_file.read_text().strip()
if not API_KEY:
    print("  ⚠ THEDERUNDOWN_KEY not set. Create .therundown_key or export it.")

BASE_URL = "https://therundown.io/api/v2"

# football-data.org API v4 — env var → config.yaml
FOOTBALL_DATA_KEY = os.environ.get("FOOTBALL_DATA_KEY", "")
FOOTBALL_DATA_COMPETITIONS: list[str] = []
if not FOOTBALL_DATA_KEY:
    try:
        import yaml
        _cfg = yaml.safe_load((REPO_ROOT / "config.yaml").read_text())
        _fdo = _cfg.get("football_data_org", {})
        FOOTBALL_DATA_KEY = _fdo.get("api_key", "")
        FOOTBALL_DATA_COMPETITIONS = _fdo.get("competitions", [])
    except Exception:
        pass
FOOTBALL_DATA_BASE = "https://api.football-data.org/v4"

FOOTBALL_SPORTS = [
    (18, "FIFA World Cup"),
    (10, "MLS"),
]

EXTRA_SPORTS = [
    (11, "EPL"),
    (14, "La Liga"),
    (15, "Serie A"),
    (13, "Bundesliga"),
    (12, "Ligue 1"),
    (16, "UEFA Champions League"),
    (17, "UEFA Europa League"),
]

AFFILIATE_NAMES = {
    3: "Pinnacle", 28: "HardRock", 27: "Bet365", 26: "Polymarket",
    25: "Kalshi", 24: "theScore Bet", 23: "FanDuel", 22: "BetMGM",
    19: "DraftKings", 21: "Unibet", 12: "Bodog", 2: "Bovada",
    16: "Matchbook", 6: "BetOnline", 11: "Lowvig", 4: "Sportsbetting",
    14: "Intertops", 18: "YouWager",
}

USER_AGENT = "Datagateway/1.0 (Football; +https://github.com/jtoemion/Datagateway)"
CACHE_TTL = 600  # 10 minutes


def fetch_events(sport_id: int, sport_name: str, date: str) -> list[dict]:
    """Fetch events for a sport on a given date."""
    cache_key = f"fifa:{sport_id}:{date}"
    cached = cache_get(cache_key, ttl_seconds=CACHE_TTL)

    if cached:
        import json
        try:
            data = json.loads(cached)
            events = data.get("events", [])
            print(f"  [cached] {sport_name} ({sport_id}): {len(events)} events")
            return events
        except json.JSONDecodeError:
            pass

    url = f"{BASE_URL}/sports/{sport_id}/events/{date}?market_ids=1,2"
    try:
        resp = requests.get(
            url,
            headers={"X-TheRundown-Key": API_KEY, "User-Agent": USER_AGENT},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        cache_set(cache_key, resp.text, ttl_seconds=CACHE_TTL)
        events = data.get("events", [])
        print(f"  [fresh] {sport_name} ({sport_id}): {len(events)} events")
        return events
    except Exception as e:
        print(f"  [error] {sport_name} ({sport_id}): {e}")
        return []


def fetch_event_odds(event_id: str) -> list[dict]:
    """Fetch detailed odds for a specific event."""
    cache_key = f"fifa_odds:{event_id}"
    cached = cache_get(cache_key, ttl_seconds=CACHE_TTL)
    if cached:
        import json
        try:
            return json.loads(cached)
        except json.JSONDecodeError:
            pass

    url = f"{BASE_URL}/events/{event_id}?market_ids=1,2,3"
    try:
        resp = requests.get(
            url,
            headers={"X-TheRundown-Key": API_KEY, "User-Agent": USER_AGENT},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        events = data.get("events", [])
        odds_data = []
        if events:
            e = events[0]
            odds_data.append(("_event_meta", e))
            for m in e.get("markets", []):
                for p in m.get("participants", []):
                    for l in p.get("lines", []):
                        line_val = l.get("line_value") or l.get("points") or l.get("handicap") or 0
                        for aid_str, price_data in l.get("prices", {}).items():
                            odds_data.append({
                                "event_id": event_id,
                                "market_id": m["market_id"],
                                "market_name": m["name"],
                                "affiliate_id": int(aid_str),
                                "affiliate_name": AFFILIATE_NAMES.get(int(aid_str), f"aff_{aid_str}"),
                                "participant_type": p.get("type", "").replace("TYPE_", ""),
                                "participant_name": p.get("name", ""),
                                "price_american": price_data.get("price"),
                                "price_decimal": price_data.get("price_decimal"),
                                "is_main_line": 1 if price_data.get("is_main_line") else 0,
                                "line_value": float(line_val) if line_val else 0,
                                "updated_at": price_data.get("updated_at", ""),
                            })
        cache_set(cache_key, str(odds_data), ttl_seconds=CACHE_TTL)
        return odds_data
    except Exception as e:
        print(f"  [error] odds fetch {event_id}: {e}")
        return []


def process_events(events: list[dict], sport_id: int):
    """Process raw API events into DB records."""
    for ev in events:
        score = ev.get("score", {})
        teams = ev.get("teams", [])
        sch = ev.get("schedule", {})

        team_away = None
        team_home = None
        for t in teams:
            if t.get("is_away"):
                team_away = t
            if t.get("is_home"):
                team_home = t

        e = {
            "event_id": ev["event_id"],
            "sport_id": sport_id,
            "event_date": ev.get("event_date", ""),
            "event_status": score.get("event_status", "STATUS_SCHEDULED"),
            "status_detail": score.get("event_status_detail", ""),
            "team_away_id": team_away.get("team_id") if team_away else None,
            "team_away": team_away.get("name") if team_away else None,
            "team_away_abbr": team_away.get("abbreviation") if team_away else None,
            "team_home_id": team_home.get("team_id") if team_home else None,
            "team_home": team_home.get("name") if team_home else None,
            "team_home_abbr": team_home.get("abbreviation") if team_home else None,
            "score_away": score.get("score_away", 0),
            "score_home": score.get("score_home", 0),
            "venue_name": score.get("venue_name", ""),
            "venue_location": score.get("venue_location", ""),
            "broadcast": score.get("broadcast", ""),
            "season_type": sch.get("season_type", ""),
            "attendance": sch.get("attendance", "0"),
            "espn_uid": ev.get("espn_uid", ""),
        }
        football_upsert_event(e)
        yield e


def main():
    init_db()
    now = datetime.now(WIB)
    today = now.strftime("%Y-%m-%d")
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")

    print(f"Datagateway — Football Fetch ({now.strftime('%Y-%m-%d %H:%M WIB')})")
    print("=" * 60)

    total_events = 0

    for sport_id, sport_name in FOOTBALL_SPORTS:
        for date in [today, tomorrow]:
            events = fetch_events(sport_id, sport_name, date)
            if not events:
                continue

            count = 0
            for e in process_events(events, sport_id):
                count += 1
                total_events += 1

            print(f"    → {count} events stored")
            time.sleep(0.5)

            sorted_events = sorted(events, key=lambda e: (
                0 if e.get("score", {}).get("event_status") == "STATUS_SCHEDULED" else 1,
                e.get("event_date", ""),
            ))
            for ev in sorted_events:
                eid = ev["event_id"]
                odds_data = fetch_event_odds(eid)
                odds_count = sum(
                    1 for o in odds_data
                    if isinstance(o, dict) and football_upsert_odds(o)
                )
                if odds_count:
                    print(f"    → odds for {eid[:16]}...: {odds_count} rows")
                time.sleep(0.5)

            break  # Only check first date per sport

    total = get_football_count()
    print(f"\n{'=' * 60}")
    print(f"  Total football events in DB: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
