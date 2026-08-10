# Tervasulka season scraper — `src/`

Python pipeline that scrapes **badmintonfinland.tournamentsoftware.com** and builds
the Tervasulka 2025-26 season report. Pure standard library (no pip installs).
Full build documentation: `../docs/README.md`.

## Run

```bash
cd src
python run_all.py          # steps 1-5
# or run individually:
python step1_list_tournaments.py
python step2_entries_winners.py
python step3_rankings.py
python step3b_crosscheck.py
python step4_build_dataset.py
python step5_build_html.py
```

Outputs land in `../data/` and `../index.html`.
HTTP responses are cached in `../.cache/` (regenerable; safe to delete to force a refresh).

## Files

| Script | Purpose |
|--------|---------|
| `twlib.py` | Shared: cookie-wall bypass + cached fetch, name/country/division/medal helpers, IDs. |
| `step1_list_tournaments.py` | Enumerate all season tournaments → `data/tournaments_raw.tsv`. |
| `step2_entries_winners.py` | Per tournament: entry list (→ club) + winners page (→ podium) → `data/_fulldata.json`. Drops entrants who only sat on event Exclude/Reserve lists (never in a real draw). |
| `step3_rankings.py` | Tervasulka ranking points from the club-filtered category lists (all pages) → `data/_rankings.json`. |
| `step3b_crosscheck.py` | Cross-check `_rankings.json` against every tournament's ranking-points page; add missing players/tournaments, fix diverging totals. |
| `step4_build_dataset.py` | Filter to ranking-list tournaments, merge into `players.json`, `tournaments.json`, `tervasulka_medals.json`, `.csv`. |
| `step5_build_html.py` | Tabbed HTML report (Overview / Players / Rankings / Tournaments / Divisions). |
| `run_all.py` | Runs all steps (1, 2, 3, 3b, 4, 5) in order. |

## How a Tervasulka player is found
- Most tournaments expose each entrant's **club** in the entry list → read directly (club = `Tervasulka` / `TeSu`).
- Some tournaments show only **nationality**; for those, winners are matched against the season-wide
  Tervasulka roster (built from the club-listing tournaments) and flagged `roster-inferred`.
- The roster is built from **entry lists** (everyone who competed), not just winners.
- Registration ≠ participation: per-event pages label entries Maindraw / Reserve list / Exclude list;
  a player benched in every event they entered is not counted as a participant (no-shows in a real
  draw still are).

## Key platform facts (encoded in `twlib.py`)
- Cookie wall: POST `ReturnUrl=/&SettingsOpen=False&CookiePurposes=1` to `/cookiewall/Save` to get the `st` cookie.
- Tournament search: POST `/find/tournament/DoSearch` with `TournamentFilter.*` fields.
- Entry list: `/tournament/<id>/Players/GetPlayersContent`. Winners: `/sport/winners.aspx?id=<id>`.
- Ranking (club-filtered): `/ranking/category.aspx?id=<publication>&category=<cat>&ogid=<club-ogid>&p=<page>&ps=100`;
  Tervasulka ogid `7C7F710E-BF72-4C15-8F3E-CABA47B736A3`. Category pages are **paginated** — walk
  every page. Names must be HTML-unescaped on both sides before matching (ä/ö/å), or matches silently fail.
- Ranking publication id (`RANKING_PUBLICATION` in `twlib.py`) is a **frozen weekly snapshot**;
  bump it to the current id (see `/ranking/`) to refresh data.
- Official ranking tournament list: `/ranking/tournaments.aspx?id=<publication>` — tournaments not
  on it award no points and are excluded from the report (medals included).
- Per-tournament points page: `/ranking/tournament.aspx?id=<publication>&tournament=<tid>` (tid from
  the tournament list) itemises every player's points at that event and is **authoritative**: a
  player's ranking *player page* can be empty even though points were awarded (seen 8/2026 — such a
  player also appears in no club-filtered category list, so step 3 alone misses them; step 3b
  recovers them from the tournament pages).
