# football-data.org API v4 — Agent Handoff Document

**Source docs:** https://www.football-data.org/documentation/quickstart (landing page, redirects to reference docs) → full reference at https://docs.football-data.org/general/v4/index.html
**Base URL for all calls:** `https://api.football-data.org/v4/`
**API key/token for this task:** `76bdde50dda94a10940c3d0ae33b8bb3` (pass as header `X-Auth-Token`)
**Current API version:** v4 (released 2022-05-20). v2 still exists but is deprecated — always use v4.

---

## 1. Authentication

Every authenticated request needs this header:

```
X-Auth-Token: 76bdde50dda94a10940c3d0ae33b8bb3
```

Example:
```bash
curl -XGET 'https://api.football-data.org/v4/competitions/PL' -H "X-Auth-Token: 76bdde50dda94a10940c3d0ae33b8bb3"
```

- Without a token: limited to 100 requests/24h, and can only hit the `areas` and `competitions` list endpoints.
- With a token (registered/free plan): 10 requests/minute. Standard plan: 30/min. Higher plans: 60/min.
- Response headers to monitor: `X-RequestCounter-Reset` (seconds until quota resets), `X-RequestsAvailable` (requests left), `X-API-Version`, `X-Authenticated-Client`.
- **Do not loop/crawl ids in bulk** — the docs explicitly warn against hammering the API (e.g. "don't write loops to crawl resources from id 0 to id 1000"); you will get banned.

---

## 2. Conceptual model (vocabulary)

- **Resource**: main building block / domain entity (Area, Competition, Match, Team, Person, Trend).
- **Subresource**: doesn't make sense standalone, always scoped under a parent resource (e.g. Standings only exist under a Competition; Matches can be a subresource of Competition, Team, or Person).
- **Filter**: query-string parameter that narrows a result set. Filters use **camelCase**. Enums are **UPPERCASE**. URIs/resource names are **lowercase**.
- All resources are accessed via their **plural** form and respond with a list by default (e.g. `/v4/teams`). Add an id to get a single resource (`/v4/teams/19`).
- A **Competition** = a football league/tournament (e.g. Premier League). Has an id, a 2-4 letter code, and a type. Contains **Seasons**, which contain **Matches** (scheduled fixtures, called "matchday" within a season). **Teams** participate in a Competition's Season.
- Note: `Season` and `Matchday` are NOT separate resources/hierarchical objects — they're just attributes you can filter on. There is no generic "round" concept.
- `Player` resource from v2 was renamed to **Person** in v4 (because referees/coaches also live there).

---

## 3. Main Resources & Endpoints

### 3.1 Area
- `GET /v4/areas` — list all areas
- `GET /v4/areas/{id}` — single area (continents have `childAreas`; countries have `parentArea`)
- No filters documented for this resource itself.
- Sample fields: `id`, `name`, `code`, `flag`, `parentAreaId`, `parentArea`, `childAreas[]`.

### 3.2 Competition
- `GET /v4/competitions` — list (filtered to your subscription by default; omit the token to see ALL available competitions)
- `GET /v4/competitions/{id or code}` — single competition (e.g. `/v4/competitions/PL`)
- **List filter:** `areas` — comma-separated area ids, e.g. `?areas=2016,2023,2025`
- Key fields: `area`, `id`, `name`, `code`, `type` (enum: `LEAGUE | LEAGUE_CUP | CUP | PLAYOFFS`), `emblem`, `currentSeason` (with `currentMatchday`, `winner`, `stages[]`), `seasons[]` (full history).

#### Subresource: Standings
- `GET /v4/competitions/{code}/standings`
- Behavior depends on competition `type`:
  - `CUP` / `PLAYOFFS` → 404 (no standings)
  - `LEAGUE_CUP` → one standing per group
  - `LEAGUE` → returns `TOTAL`, `HOME`, and `AWAY` standings
- Filters: `season` (e.g. `?season=1981`), `matchday` (e.g. `?matchday=15`), `date` (yyyy-MM-dd, e.g. `?date=2022-01-01` finds the table as it stood on that date). `season` + `matchday` can be combined, but combining them means the standings are computed live from matches only (won't reflect deducted points).
- Response shape: `filters`, `area`, `competition`, `season`, `standings[]` → each has `stage`, `type` (`TOTAL|HOME|AWAY`), `group`, `table[]` of `{position, team, playedGames, form, won, draw, lost, points, goalsFor, goalsAgainst, goalDifference}`.
- ⚠️ Past-season standings have deducted points removed over time (for data-analysis neutrality) — take a snapshot if you need historical penalty-adjusted standings.

#### Subresource: (Top) Scorers
- `GET /v4/competitions/{code}/scorers` (defaults to `limit=10`)
- Filters: `season`, `matchday` (combinable)
- Response: `count`, `filters`, `competition`, `season`, `scorers[]` → each `{player, team, goals, assists, penalties}`.

#### Subresource: Matches (under a Competition)
- `GET /v4/competitions/{code}/matches`
- Filters: `season`, `matchday`, `status` (enum), `dateFrom`+`dateTo`, `stage` (enum), `group` (enum)
- Response: `filters`, `resultSet` (count/first/last/played), `competition`, `matches[]`.

#### Subresource: Teams (under a Competition)
- `GET /v4/competitions/{code}/teams`
- Filter: `season`
- Returns the same team-list shape as the standalone Team list resource.

### 3.3 Match
- `GET /v4/matches` — today's matches across your subscribed competitions (default = "now" in UTC)
- `GET /v4/matches/{id}` — single match, very rich payload (see §3.3.1)
- `GET /v4/matches/{id}/head2head` — historical head-to-head between the two teams in that match
- **List filters:**
  | Filter | Format | Example | Notes |
  |---|---|---|---|
  | `ids` | comma-sep ints | `?ids=333,3303,3213` | fetch specific matches |
  | `date` | yyyy-MM-dd | `?date=2022-01-01` | also accepts shortcuts `YESTERDAY`/`TOMORROW` |
  | `dateFrom`/`dateTo` | yyyy-MM-dd | `?dateFrom=2022-01-01&dateTo=2022-01-10` | dateTo is **exclusive** as of v4 |
  | `status` | enum | `?status=FINISHED` | also accepts pseudo-status `LIVE` (= `IN_PLAY` + `PAUSED` combined) |

- **Match status workflow:** `SCHEDULED` → `TIMED` (once exact kickoff is known) → `IN_PLAY` → `PAUSED` (halftime) → `FINISHED`. Other terminal/abnormal states: `SUSPENDED`, `POSTPONED`, `CANCELLED`, `AWARDED`. (Lookup table also lists `EXTRA_TIME`, `PENALTY_SHOOTOUT` as status values in some contexts.)

#### 3.3.1 Single Match payload — key nodes
- `area`, `competition`, `season`, `id`, `utcDate`, `status`, `minute`, `injuryTime`, `attendance`, `venue`, `matchday`, `stage`, `group`, `lastUpdated`
- `homeTeam` / `awayTeam`: `id, name, shortName, tla, crest, coach{id,name,nationality}, leagueRank, formation, lineup[], bench[], statistics{...}`
  - `statistics` includes: `corner_kicks, free_kicks, goal_kicks, offsides, fouls, ball_possession, saves, throw_ins, shots, shots_on_goal, shots_off_goal, yellow_cards, yellow_red_cards, red_cards`
- `score`: `winner` (`HOME_TEAM|AWAY_TEAM|DRAW`), `duration` (`REGULAR|EXTRA_TIME|PENALTY_SHOOTOUT`), `fullTime{home,away}`, `halfTime{home,away}`, and since v4 a `regularTime` node (score after 90 min if there was extra time/penalties). See §5 below for full detail on scores.
- `goals[]`: `{minute, injuryTime, type(REGULAR|OWN|PENALTY), team, scorer, assist, score}` — `score` here shows the running score at that moment.
- `penalties[]` (shootout only): `{player, team, scored}`
- `bookings[]`: `{minute, team, player, card(YELLOW|YELLOW_RED|RED)}`
- `substitutions[]`: `{minute, team, playerOut, playerIn}`
- `odds`: `{homeWin, draw, awayWin}` (decimal odds)
- `referees[]`: `{id, name, type, nationality}` — `type` enum: `REFEREE | ASSISTANT_REFEREE_N1/N2/N3 | FOURTH_OFFICIAL | VIDEO_ASSISTANT_REFEREE_N1/N2/N3`

**Automatic folding / response-size control:** by default, list endpoints for matches hide lineups/bookings/subs/goals to save bandwidth. Control this with request headers (boolean `true`/`false`):
```
X-Unfold-Lineups
X-Unfold-Bookings
X-Unfold-Subs
X-Unfold-Goals
```

### 3.4 Team
- `GET /v4/teams` — list resource (all teams)
- `GET /v4/teams/{id}` — single team. Key fields: `area, id, name, shortName, tla, crest, address, website, founded, clubColors, venue, runningCompetitions[]` (competitions the team started the season in — stays listed even after elimination), `coach{id, firstName, lastName, name, dateOfBirth, nationality, contract{start,until}}`, `marketValue`, `squad[]` (each player: `id, firstName, lastName, name, position, dateOfBirth, nationality, shirtNumber, marketValue, contract`), `staff[]`, `lastUpdated`.

#### Subresource: Matches (under a Team)
- `GET /v4/teams/{id}/matches`
- Filters: `dateFrom`/`dateTo`, `season`, `status`, `venue` (`HOME|AWAY`), `limit` (integer 1–500, default 100)
- Response: `filters`, `resultSet{count, competitions, first, last, played, wins, draws, losses}`, `matches[]`.
- Note: matches returned here lack lineups/bookings/etc. unless you set the `X-Unfold-*` headers above.

### 3.5 Person
- `GET /v4/persons/{id}` — mostly football players (~79% of persons in their DB), but also referees/staff.
- Key fields: `id, name, firstName, lastName, dateOfBirth, nationality, position, shirtNumber, lastUpdated, currentTeam{...}` (full team object including `runningCompetitions` and `contract`).

#### Subresource: Matches (under a Person)
- `GET /v4/persons/{id}/matches`
- Filters:
  | Filter | Values |
  |---|---|
  | `lineup` | `STARTING \| BENCH` |
  | `e` (event) | `GOAL \| ASSIST \| SUB_IN \| SUB_OUT` |
  | `dateFrom` / `dateTo` | yyyy-MM-dd |
  | `competitions` | comma-separated codes, e.g. `PL,FAC` |
  | `limit` | integer 1–100 (default 15) |
  | `offset` | integer 1–100 |
- Response includes an `aggregations{}` block: `matchesOnPitch, startingXI, minutesPlayed, goals, ownGoals, assists, penalties, subbedOut, subbedIn, yellowCards, yellowRedCards, redCards` — computed over the filtered match set.
- Useful examples from docs:
  - Last 10 matches subbed out: `/v4/persons/{id}/matches?e=SUB_OUT&limit=10`
  - Last matches scored in: `/v4/persons/{id}/matches?e=GOAL&limit=5`

### 3.6 Trend (newer resource — extensive derived "form" data)
- `GET /v4/trends/?date=2025-12-06` (also supports `dateFrom`/`dateTo`)
- Purpose: precomputed form/strength metrics per team over a rolling window of recent matches (default window = last 5 matches), expressed as **averages** (`avg_*`) or **percentages** (`pct_*`, 0–1 scale).
- Filters:
  | Filter | Values | Notes |
  |---|---|---|
  | `date` | yyyy-MM-dd | defaults to today; takes precedence over dateFrom/dateTo if present |
  | `dateFrom` / `dateTo` | yyyy-MM-dd | dateTo is exclusive |
  | `competitions` | comma-separated codes | e.g. `?competitions=PL,DED` |
  | `window` | integer 1–15 | how many past matches to compute trend over (default 5) |
  | `consider_side` | boolean flag (just include the param) | if set, only home matches count toward the home team's trend and vice versa |
- Response: `meta{filters, result_set}`, `trends[]` — each trend entry has `id, status, competition, matchday, season, homeTeam, awayTeam, trend{home{...}, away{...}}, odds{odds_1x2, asian_handicap, btts, over_under}, score, utcDate, lastUpdated`.
- **Data points available inside `trend.home` / `trend.away`** (full table — useful for betting/analytics use cases):
  `avg_goals, avg_goals_conceded, avg_goals_scored, avg_points, competitions, form (e.g. "WDWWD", newest-first), match_ids[], pct_1st_hf_o_05/15/25, pct_1st_hf_u_05/15/25, pct_2nd_hf_o_05/15/25, pct_2nd_hf_u_05/15/25, pct_bts (both teams scored), pct_draws, pct_fts (failed to score), pct_losses, pct_o_05/15/25/35 (over X.5 total goals), pct_u_05/15/25/35, pct_wins, team_id, window_end_date, window_start_date`.
  - Naming convention: `o_05` = "over 0.5", `u_15` = "under 1.5", `1st_hf` / `2nd_hf` = first/second half.

---

## 4. Defaults & Behavior Rules (important — easy to get wrong)

- **Date defaults to "now" in UTC.** E.g. `GET /v4/matches` with no filters returns only **today's** matches. `GET /v4/teams/{id}` returns the squad for the **current season**.
- **Current season** = simply the season with the latest start date for that competition (not separately computed).
- **Current matchday** algorithm: take the last-played and next-scheduled match of the season.
  - If they're on the same matchday, use that.
  - If the gap to the next match is <36h, OR the gap since the last match is >60h → snap to the next match's matchday.
  - Matchday only ever increases during a season (never reverts), even if catch-up games are played out of order.
- **dateTo is exclusive** (changed in v4 from v2): `?dateTo=2022-02-02` returns matches up to and including 2022-02-01 23:59 UTC, NOT including Feb 2.
- **null is a valid value** — e.g. score before kickoff, attendance for obscure competitions. Empty lists are valid too.
- **True data types** are used — scores are integers, not strings.
- `runningCompetitions` (on Team) and `squad` (on Team) include everything the team started the season with, even after later elimination from a cup, etc.
- **Captain field removed** in v4 (no longer supported).
- Filtering by relative date shortcuts: `YESTERDAY`, `TOMORROW` are valid values for `date`, e.g. `?date=YESTERDAY`.

---

## 5. Scores in depth (extra-time / penalty shootouts)

All score data lives in the `score` node; every attribute defaults to `null` until relevant.

- `score.fullTime` — becomes `0/0` as soon as status hits `IN_PLAY`; holds the running/final score.
- `score.halfTime` — populates once status hits `PAUSED` (end of first half) and does not change again.
- `score.duration` — `REGULAR` (default) | `EXTRA_TIME` | `PENALTY_SHOOTOUT`. Tells you how the match concluded (or, if still in progress, an additional live status).
- `score.extraTime` / `score.penalties` — appear and start counting from 0 once `duration` becomes `EXTRA_TIME` / `PENALTY_SHOOTOUT` respectively; they count ONLY goals scored within that phase.
- `score.regularTime` (new in v4) — goals scored within the first 90 minutes, useful even if the match went to extra time/penalties.
- Distinction: "ended **in** penalty shootout" = use `score.penalties`; "ended **after** a penalty shootout" = use `score.fullTime`.

Example (Germany won EC 1996 QF after penalties):
```json
"score": {
  "winner": "HOME_TEAM",
  "duration": "PENALTY_SHOOTOUT",
  "fullTime": {"homeTeam": 7, "awayTeam": 6},
  "halfTime": {"homeTeam": 1, "awayTeam": 1},
  "regularTime": {"homeTeam": 1, "awayTeam": 1},
  "extraTime": {"homeTeam": 0, "awayTeam": 0},
  "penalties": {"homeTeam": 6, "awayTeam": 5}
}
```

---

## 6. Errors

JSON error body shape: `{ "error": "Argument 'id' is expected to be an integer in a specific range." }`

| Code | Meaning |
|---|---|
| 400 | Bad Request — a filter value doesn't match its expected data type |
| 403 | Restricted Resource — needs auth, needs a paid tier, or doesn't exist in this API version |
| 404 | Not Found |
| 429 | Too Many Requests — rate limit exceeded (see §1) |
| 5xx | Server-side fault (not your fault) |

---

## 7. Full Enum Reference

| Resource | Attribute | Values |
|---|---|---|
| Competition | type | `LEAGUE \| LEAGUE_CUP \| CUP \| PLAYOFFS` |
| Team | type | `MEN_CLUB \| MEN_NATIONAL \| WOMEN_CLUB \| WOMEN_NATIONAL` |
| Match | status | `SCHEDULED \| TIMED \| IN_PLAY \| PAUSED \| EXTRA_TIME \| PENALTY_SHOOTOUT \| FINISHED \| SUSPENDED \| POSTPONED \| CANCELLED \| AWARDED` (plus pseudo-status `LIVE` as a filter-only shortcut for `IN_PLAY`+`PAUSED`) |
| Match | stage | `FINAL \| THIRD_PLACE \| SEMI_FINALS \| QUARTER_FINALS \| LAST_16 \| LAST_32 \| LAST_64 \| ROUND_4 \| ROUND_3 \| ROUND_2 \| ROUND_1 \| GROUP_STAGE \| PRELIMINARY_ROUND \| QUALIFICATION \| QUALIFICATION_ROUND_1 \| QUALIFICATION_ROUND_2 \| QUALIFICATION_ROUND_3 \| PLAYOFF_ROUND_1 \| PLAYOFF_ROUND_2 \| PLAYOFFS \| REGULAR_SEASON \| CLAUSURA \| APERTURA \| CHAMPIONSHIP_ROUND \| RELEGATION_ROUND` |
| Match | group | `GROUP_A` through `GROUP_L` |
| Penalty | type | `MATCH \| SHOOTOUT` |
| Score | duration | `REGULAR \| EXTRA_TIME \| PENALTY_SHOOTOUT` |
| Card | type | `YELLOW \| YELLOW_RED \| RED` |
| Goal | type | `REGULAR \| OWN \| PENALTY` |
| Referee | type/role | `REFEREE \| ASSISTANT_REFEREE_N1/N2/N3 \| FOURTH_OFFICIAL \| VIDEO_ASSISTANT_REFEREE_N1/N2/N3` |

## 8. Request & Response Headers Reference

**Request headers you can set:**
| Header | Values | Purpose |
|---|---|---|
| `X-Auth-Token` | your token string | authentication |
| `X-Unfold-Lineups` | `true\|false` | include/exclude lineups in match list responses |
| `X-Unfold-Bookings` | `true\|false` | include/exclude bookings |
| `X-Unfold-Subs` | `true\|false` | include/exclude substitutions |
| `X-Unfold-Goals` | `true\|false` | include/exclude goals |

**Response headers to read:**
| Header | Example | Meaning |
|---|---|---|
| `X-API-Version` | `v4` | API version serving the request |
| `X-Authenticated-Client` | `Jimbo Jones` | detected client name, or `anonymous` |
| `X-RequestCounter-Reset` | `23` | seconds until your rate-limit counter resets |
| `X-RequestsAvailable` | `21` | requests left before you get blocked |

## 9. All Filters — Quick Reference Table

| Filter | Format | Description |
|---|---|---|
| `id` / `ids` | integer or comma-sep integers | resource id(s) |
| `matchday` | integer | drill into one matchday |
| `areas` | comma-sep area ids | restrict by area |
| `season` | 4-digit year string | defaults to current season's start year |
| `venue` | `HOME\|AWAY` | restrict matches by venue |
| `competitions` | comma-sep competition codes | restrict by competition |
| `date` | yyyy-MM-dd (or `YESTERDAY`/`TOMORROW`) | single date |
| `dateFrom` / `dateTo` | yyyy-MM-dd | date range; `dateTo` is **exclusive** |
| `status` | enum (see above) | match status filter |
| `stage` | enum | competition stage |
| `group` | enum (`GROUP_A`..`GROUP_L`) | group filter |
| `lineup` | `STARTING\|BENCH` | player's role in the match |
| `e` | `GOAL\|ASSIST\|SUB_IN\|SUB_OUT` | player event filter (Person/matches) |
| `limit` | integer, range varies by endpoint (1–100 or 1–500) | page size |
| `offset` | integer | pagination offset |
| `window` | integer 1–15 (Trend only) | rolling window size for trend calc |
| `consider_side` | flag, no value needed (Trend only) | home/away-specific trend calc |

---

## 10. League Codes (use instead of numeric ids — more memorable)

Format: `competition_id | code | name | country`. Use the **code** in place of an id anywhere a competition id is expected, e.g. `/v4/competitions/PL` instead of `/v4/competitions/2021`.

Selected major leagues (full table has ~80 entries covering all continents — see source doc for the complete list):

| Code | Competition | Country |
|---|---|---|
| PL | Premier League | England |
| ELC | Championship | England |
| FAC | FA Cup | England |
| FLC | Football League Cup | England |
| BL1 | Bundesliga | Germany |
| BL2 | 2. Bundesliga | Germany |
| DFB | DFB-Pokal | Germany |
| SA | Serie A | Italy |
| CIT | Coppa Italia | Italy |
| PD | Primera Division (La Liga) | Spain |
| CDR | Copa del Rey | Spain |
| FL1 | Ligue 1 | France |
| FL2 | Ligue 2 | France |
| DED | Eredivisie | Netherlands |
| PPL | Primeira Liga | Portugal |
| BSA | Campeonato Brasileiro Série A | Brazil |
| ASL | Liga Profesional | Argentina |
| MLS | MLS | United States |
| CL | UEFA Champions League | Europe |
| EL | UEFA Europa League | Europe |
| UCL | UEFA Conference League | Europe |
| EC | European Championship | Europe |
| WC | FIFA World Cup | World |
| CLI | Copa Libertadores | South America |
| CA | Copa America | South America |

(Full list of ~80 codes including qualification tournaments, lower divisions, and playoffs is in the source doc at `lookup_tables.html#_league_codes` — fetch on demand if a code outside this shortlist is needed.)

---

## 11. Ready-to-use Sample Requests (from official docs)

```bash
# Last finished match for Man City (team id 65)
curl -XGET 'https://api.football-data.org/v4/teams/65/matches?status=FINISHED&limit=1' -H "X-Auth-Token: 76bdde50dda94a10940c3d0ae33b8bb3"

# Next scheduled match for Newcastle (team id 67)
curl -XGET 'https://api.football-data.org/v4/teams/67/matches?status=SCHEDULED&limit=1' -H "X-Auth-Token: 76bdde50dda94a10940c3d0ae33b8bb3"

# Today's matches across subscribed competitions
curl -XGET 'https://api.football-data.org/v4/matches' -H "X-Auth-Token: 76bdde50dda94a10940c3d0ae33b8bb3"

# All Champions League matches
curl -XGET 'https://api.football-data.org/v4/competitions/CL/matches' -H "X-Auth-Token: 76bdde50dda94a10940c3d0ae33b8bb3"

# Upcoming matches for Real Madrid (team id 86)
curl -XGET 'https://api.football-data.org/v4/teams/86/matches?status=SCHEDULED' -H "X-Auth-Token: 76bdde50dda94a10940c3d0ae33b8bb3"

# Premier League matchday 11 fixtures
curl -XGET 'https://api.football-data.org/v4/competitions/PL/matches?matchday=11' -H "X-Auth-Token: 76bdde50dda94a10940c3d0ae33b8bb3"

# Eredivisie standings
curl -XGET 'https://api.football-data.org/v4/competitions/DED/standings' -H "X-Auth-Token: 76bdde50dda94a10940c3d0ae33b8bb3"

# Top 10 scorers, Serie A
curl -XGET 'https://api.football-data.org/v4/competitions/SA/scorers' -H "X-Auth-Token: 76bdde50dda94a10940c3d0ae33b8bb3"

# Trend data for all matches on a given date
curl -XGET 'https://api.football-data.org/v4/trends/?date=2025-12-06' -H "X-Auth-Token: 76bdde50dda94a10940c3d0ae33b8bb3"
```

---

## 12. Client libraries / coding-language guides (official, linked from docs)

The "Coding a client" section of the docs links language-specific quickstarts. Two routes: a raw HTTP call (works in any language) or a higher-abstraction library (Docker/compose-based local infra). Guides exist for:
- Bash → https://docs.football-data.org/general/v4/coding/bash.html
- Java → https://docs.football-data.org/general/v4/coding/java.html
- Groovy → https://docs.football-data.org/general/v4/coding/groovy.html
- PHP → https://docs.football-data.org/general/v4/coding/php.html
- Python → https://docs.football-data.org/general/v4/coding/python.html
- Elixir → https://docs.football-data.org/general/v4/coding/elixir.html

(Not fetched in this handoff — pull on demand if the target implementation language is one of these and code samples are needed.)

---

## 13. Misc Notes for the Implementing Agent

- A **Postman collection** of all endpoints is importable from a link on the original quickstart page (`getpostman.com/collections/f3449621c47b66b53725`) if exploratory testing via Postman is useful.
- Free tier = `TIER_THREE` permission level appears in some response `filters` blocks — this is just metadata about your subscription tier, not something you set yourself.
- For analytics/betting-style features, the **Trend resource** (§3.6) is the most calculation-rich endpoint — it pre-computes rolling form, over/under percentages, BTTS rate, and includes bookmaker `odds` (1X2, Asian handicap, over/under) per match.
- Treat all resource ids returned in responses (team id, competition id, person id, match id) as the canonical join keys across endpoints — e.g. `homeTeam.id` from a Match response is the same id you'd query at `/v4/teams/{id}`.
- Always prefer **league codes** over raw competition ids in URLs for readability — both work identically.
