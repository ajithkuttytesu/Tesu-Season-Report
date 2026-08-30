# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A scraper + report generator that collects per-season tournament results for all players of the Tervasulka badminton club from **badmintonfinland.tournamentsoftware.com**, and renders self-contained report pages into `Output/` — `index.html` for the ongoing season, `<season>.html` (e.g. `2025-26.html`) frozen per finished season, `tervasulka-report.html` as the all-seasons single share file — plus per-season datasets (`data/<season>/*.json`, `*.csv`). Full build documentation lives in `docs/README.md`; dataset schemas in `data/README.md`; per-script summaries in `src/README.md`. Keep all three in sync when changing the pipeline.

## Commands

Python 3, standard library only (no pip installs). On this machine invoke Python with `py`.

```
cd src
py refresh.py                     # monthly update of the ongoing season (preferred)
py run_all.py [--season 2025-26]  # full pipeline (steps 1, 2, 3, 3b, 4, 5) for one season
py step3_rankings.py [--season X] # or any individual step
py build_share.py                 # single-file share variant (all seasons in one HTML)
```

There are no tests or linters. Verification is done by re-running the affected steps and inspecting the outputs in `data/<season>/` and the rendered page.

## Architecture

**Season registry**: `src/seasons.json` holds one entry per season — date range, ISO-week window, pinned ranking `publication` id, member-discovery category ids, `status` (`ongoing`/`final`), `generated` date. `twlib.configure(season)` points module globals (`DATA=data/<season>`, `CACHE=.cache/<season>`, `RANKING_PUBLICATION`, `ID_CATEGORIES`, week window) at one season; default is the single ongoing entry. Every entry point (`--season` flag) re-calls it. Pinning the publication per season is what freezes finished seasons — step 4 filters tournaments against that publication, so an unpinned/bumped id would drop an archived season's tournaments (this hazard is now structurally prevented).

Six-step pipeline in `src/`; each step reads the previous step's output from `data/<season>/` and writes back into it:

1. `step1_list_tournaments.py` — enumerate all season tournaments → `tournaments_raw.tsv`
2. `step2_entries_winners.py` — entry lists, season roster, per-event participation filtering, podium results → `_fulldata.json`
3. `step3_rankings.py` — ranking points per player from the season's pinned ranking publication → `_rankings.json`
4. `step3b_crosscheck.py` — verify/patch `_rankings.json` against per-tournament points pages (authoritative)
5. `step4_build_dataset.py` — filter to ranking-list tournaments, merge identities → `players.json`, `tournaments.json`, `tervasulka_medals.json`, `.csv`
6. `step5_build_html.py` — render the report page (single self-contained page, inline CSS/JS + logo from `assets/`, themed to tervasulka.fi, season-switcher nav) into `Output/`: `index.html` when the season is ongoing, `<season>.html` when final

`src/refresh.py` is the monthly driver: detects the current publication id from `/ranking/`, validates category ids, stamps `seasons.json`, invalidates volatile caches (search pages, unsettled tournaments), runs steps 1–5, and re-renders finished seasons' pages so the nav stays consistent.

`src/twlib.py` is the shared library: season registry + `configure()`, cookie-wall bypass + cached `fetch()`, site identifiers (`TERVA_RANKING_OGID`, `CLUB_NAMES`), name identity (`tokens()`, `NAME_ALIASES`, `DISPLAY_OVERRIDES`), tournament identity (`norm_tname()` + ISO week), `in_season()`, division/medal classification.

All HTTP fetches are cached in `.cache/<season>/` (gitignored). A cached file is used as-is; ranking cache names embed the publication id so a bump self-invalidates. Files prefixed `_` in `data/<season>/` are regenerable intermediates; the rest are the published dataset. For a `final` season, git is authoritative — never let a rebuild change `data/<final-season>/`.

## Domain rules that must not be broken

These encode hard-won corrections (details and incident examples in `docs/README.md` § Pitfalls):

- **Per-tournament points pages are authoritative** for ranking points. A player's ranking *player page* can be empty or under-report even though points were awarded — that's why step 3b exists. Never remove step 3b or trust player pages alone.
- **Never credit ranking rows by name alone** — member id is the identity. Name-matching is only trusted for confirmed TeSu entrants of that specific tournament, and only when it doesn't contradict a known member id.
- **Registration ≠ participation.** Entry lists include players who never played. Per-event pages label entries Maindraw / Reserve list (`elt9998`) / Exclude list (`elt9999`); a player benched in every event they entered did not participate. No-shows in a real draw *do* count.
- **A ranking publication is a frozen snapshot.** Re-fetching the same `RANKING_PUBLICATION` id never brings new data; refreshing means bumping the id (procedure in `docs/README.md` § Maintenance).
- **Ranking category pages are paginated** — walk every page (`p=<n>&ps=100`) or silently lose players below the fold.
- **Only tournaments on the official ranking list** (`/ranking/tournaments.aspx?id=<publication>`) are published; step 4 drops the rest, including their medals.
- **Names vary across pages** (case, transliteration, `Last, First` vs `First Last`, organiser typos). Match via token sets; genuine spelling differences need a `NAME_ALIASES` entry in `twlib.py`. HTML-unescape names on both sides before matching (ä/ö/å) or matches silently fail.
- **Match tournaments** between the calendar and ranking pages on `(norm_tname(name), ISO week)`, never raw names.
- Player-page and tournament-page event labels use different vocabularies (English `MD B` vs Finnish `MN B`); `division()` handles both. Step 3b compares totals with a 0.06/event tolerance because player pages round to one decimal.

## Maintenance recipes

`docs/README.md` § Maintenance has the exact steps for the three routine tasks: the monthly refresh (`py refresh.py` — handles publication bump, cache invalidation and the generated date automatically), adding a name alias (edit `twlib.py`, re-run steps 4–5; applies forward only — touching a `final` season's page is a deliberate act), and starting a new season (flip old entry to `final`, append new entry to `seasons.json`, run `refresh.py`).
