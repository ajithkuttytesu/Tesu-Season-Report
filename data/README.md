# Tervasulka season datasets

Scraped from **badmintonfinland.tournamentsoftware.com**. One folder per season
(`2025-26/`, `2026-27/`, …), each holding the same set of files documented
below. The season registry (dates, pinned ranking publication, status) is
`../src/seasons.json`. Regenerate the ongoing season with `../src/refresh.py`,
any season with `../src/run_all.py --season <key>` (full build docs:
`../docs/README.md`). A `final` season's folder is frozen — git is
authoritative for it.

Only tournaments on the **official ranking list** of the pinned ranking publication
(`/ranking/tournaments.aspx?id=…`) are included; local pool, school and club-internal
events award no ranking points and are excluded, medals included.

## Published files

| File | Format | Contents |
|------|--------|----------|
| `players.json` | JSON | **Per-player record** — tournaments entered, medals (G/S/B), ranking points + breakdown, ranking-page link. Built from entry lists, so includes non-medalists. |
| `tournaments.json` | JSON | Catalogue of the season's ranking-list tournaments + metadata and links. |
| `tervasulka_medals.json` | JSON | Podium results grouped by tournament. |
| `tervasulka_medals.csv` | CSV (UTF-8 BOM) | Flat one-row-per (player, medal); has a `division` column. Opens in Excel. |

Intermediates (regenerable, used between pipeline steps): `tournaments_raw.tsv`,
`_fulldata.json` (entries+winners), `_rankings.json` (ranking points).

## `players.json` (array)
`name`, `tournaments_played`, `tournaments` (list of `[date, name]`), `gold`, `silver`,
`bronze`, `total_medals`, `medals` (list of `{date,tournament,event,division,medal,place,partners,confidence}`),
`ranking_points` (this-season total), `ranking_tournaments` (per-tournament breakdown:
`{tournament,date,week,url,points,events[{event,placing,points}]}`), `ranking_member_id`, `ranking_url`.

## `tournaments.json` (array)
`date`, `name`, `location`, `url`, `winners_url`, `tournament_id`,
`entry_list_shows` (`club` | `country_only`), `players`, `tervasulka_entrants`,
`tervasulka_medals`, `has_published_results`.

## `tervasulka_medals.json` (array)
Per tournament: `date`, `tournament`, `location`, `url`, `medals[]` with
`event`, `division`, `place`, `medal`, `tervasulka_players`, `all_players_in_entry`, `confidence`.

## Notes
- **Roster source**: tournament entry lists (everyone who competed), not the winners list.
- **Divisions**: events classified into `Valio/Elite`, `A`, `B`, `C`, `D`, `Junior`, `Senior`.
- **Ranking points**: read from each player's official ranking page, counting only results from
  **this season's** tournaments (the season's ISO-week window from `seasons.json` — the official ranking total uses a
  longer rolling window that mixes in the previous season). All divisions are included (open, junior
  U-age, senior/veteran 35+…). Identical rows that re-rank the same result across class lists are
  de-duplicated. A few results are foreign events (Sweden, international series) not in the domestic
  catalogue; their points count but they have no domestic link.
- **`confidence`**: `confirmed` (club read from that tournament's entry list) or
  `roster-inferred` (entry list showed nationality only; club matched against the season roster).
- **Coverage vs PDF calendar** (2025-26): all 52 individual national tournaments from the official PDF are included
  (plus regional/local events). Out of scope: Arctic Open & BE Junior Circuit (BWF platform) and
  Joukkue-SM & Junioreiden joukkuekisa (team events — winners are clubs, not individuals).
