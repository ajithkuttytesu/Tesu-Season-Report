# Tervasulka Season Report — build documentation

How the Tervasulka season reports (`Output/index.html` for the ongoing season,
`Output/<season>.html` for finished ones) and their datasets (`data/<season>/*.json`,
`*.csv`) are built from **badmintonfinland.tournamentsoftware.com**.

Last updated: 2026-08-23.

## Seasons

The project holds one report per season. All season-specific values live in
**`src/seasons.json`** — one entry per season with its date range
(`start`/`end`, used by the tournament search), ISO-week window
(`week_start`/`week_end`, used to filter ranking results), pinned ranking
`publication` id, member-discovery `categories`, `status`
(`ongoing` | `final`) and `generated` date.

Per-season layout:

```
src/seasons.json           season registry (the only place season values live)
data/<season>/             dataset of one season (e.g. data/2025-26/)
.cache/<season>/           cached HTTP fetches of one season
assets/logo-tervasulka.svg shared, season-neutral assets
Output/index.html          report page of the ONGOING season
Output/<season>.html       frozen report page of each finished season
Output/tervasulka-report.html  single-file share variant: ALL seasons in one HTML
```

`twlib.configure(season)` points the pipeline at one season (default: the
single `ongoing` entry); every step accepts `--season <key>`. A finished
season's page is frozen: its data, publication id and `generated` date never
change, and it is only re-rendered to keep the season-switcher navigation in
sync (deterministic, no network).

## Overview

The build is a six-step Python pipeline in `src/`. Each step reads the output
of the previous one and writes into `data/<season>/`; the final step renders
the self-contained report page into `Output/`.

```
tournamentsoftware.com
        │
        ▼
step1_list_tournaments.py   → data/<season>/tournaments_raw.tsv  (all season events)
        ▼
step2_entries_winners.py    → data/<season>/_fulldata.json       (entries, roster, podiums)
        ▼
step3_rankings.py           → data/<season>/_rankings.json       (ranking points per player)
        ▼
step3b_crosscheck.py        → data/<season>/_rankings.json       (verified/patched against
        ▼                                                         per-tournament points pages)
step4_build_dataset.py      → data/<season>/players.json, tournaments.json,
                              tervasulka_medals.json, tervasulka_medals.csv
        ▼
step5_build_html.py         → Output/index.html | <season>.html  (the report page)
```

Run everything with:

```
cd src
py refresh.py                    # monthly update of the ongoing season (preferred)
py run_all.py [--season 2025-26] # plain pipeline run for one season
py step1_... [--season ...]      # or run the steps individually
```

Every HTTP fetch is cached on disk in `.cache/<season>/` (see *Caching*
below), so re-runs are fast and only fetch what is missing.

## Requirements

- Python 3 (standard library only — no third-party packages). Invoke with `py`
  on Windows.
- Network access to `badmintonfinland.tournamentsoftware.com`.

## Shared library — `src/twlib.py`

Everything the steps have in common:

- **Site session / cookie wall.** The site redirects new visitors to a cookie
  consent wall. `fetch()` first POSTs the consent form once per process, then
  requests pages with a browser User-Agent. `fetch(path, cache_name=...)`
  returns the cached copy when one exists.
- **Identifiers.**
  - `TERVA_RANKING_OGID` — Tervasulka's organisation GUID, used to club-filter
    ranking category pages.
  - `RANKING_PUBLICATION` — the weekly ranking publication id the configured
    season is pinned to (per-season, from `seasons.json`; set by
    `configure()`). **A publication is a fixed snapshot**: re-fetching the
    same id returns the same data, so refreshing means bumping the ongoing
    season's id — `refresh.py` does this automatically (see *Maintenance*).
    A finished season keeps its pinned id forever, which is what freezes it.
  - `CLUB_NAMES` — strings that count as Tervasulka in entry lists
    (`tervasulka`, `tesu`).
- **Name identity.** `tokens(name)` turns a name into an order-independent
  `frozenset` of lowercase tokens, so `"Waas, Nipun"` and `"Nipun Waas"` map to
  the same identity key. Two manual tables patch the cases this cannot solve:
  - `NAME_ALIASES` — maps a variant's token key to the canonical key
    (transliteration differences such as *Volkhonskaja* → *Volkhonskaia*;
    initials such as *Shreeharsha B V* → *Shreeharsha Banavasi Venkatesh*).
  - `DISPLAY_OVERRIDES` — forces the display name when the automatic pick
    among the observed spellings would choose the wrong one.
- **Tournament identity.** `norm_tname()` (drop parentheticals and years,
  lowercase) plus `isoweek()` of the start date form the key used to match a
  tournament between the calendar, the ranking result rows, and the ranking
  tournament list.
- **Ranking-list filter.** `ranking_tournaments()` scrapes
  `/ranking/tournaments.aspx?id=<publication>` — the official list of
  tournaments that award ranking points — into a set of
  `(normalised name, ISO week)` keys. **Only tournaments on this list are
  published**; step 4 drops the rest (local pool competitions, school and
  club-internal events), including any medals won there.
- **Classification.** `division(event)` buckets an event label into
  `Valio/Elite`, `A`, `B`, `C`, `D`, `Junior`, `Senior` or `Other`
  (e.g. `BS U13` → Junior, `XD 35` → Senior, `Nelinpeli - Kilpa` → A).
  `is_medal`/`medal_name` map placings 1 / 2 / 3 / 3-4 to Gold/Silver/Bronze.

## Step 1 — list the season's tournaments

`step1_list_tournaments.py` pages through the site's tournament search
(`/find/tournament/DoSearch`, badminton = SportID 2) restricted to the season
date range (2025-08-01 … 2026-06-30) and writes one line per tournament to
`data/tournaments_raw.tsv`: `date <TAB> guid <TAB> name <TAB> location`.

## Step 2 — entry lists, roster, podium results

`step2_entries_winners.py` reads three things per tournament from step 1:

1. **Entry list** (`/tournament/<gid>/Players/GetPlayersContent`). Records each
   entrant and, when shown, their club. Tournaments that expose clubs are
   `clubmode`; some only show nationality (`country_only`). Every entrant whose
   club matches `CLUB_NAMES` joins the **season roster** — the set of confirmed
   Tervasulka players with the tournaments they entered.
2. **Event entry lists** (`/sport/event.aspx?id=<gid>&event=<n>`, events
   enumerated from `/sport/events.aspx?id=<gid>`). The tournament-wide entry
   list also contains players who registered but never played: each event page
   labels its entries **Maindraw** (or another real draw), **Reserve list**
   (row class `elt9998`) or **Exclude list** (`elt9999`). A player whose every
   event entry is benched (reserve/exclude only, in no real draw anywhere in
   the tournament) is removed from the tournament's entrant lists — they did
   not participate. **No-shows are kept**: they sit in a real draw and simply
   earned no points. Event pages are fetched only for tournaments with a
   Tervasulka connection; tournaments that publish no event entry tables are
   left unfiltered.
3. **Winners page** (`/sport/winners.aspx?id=<gid>`). Parses podium placings
   per event. A placing is a Tervasulka *hit* when the player is a Tervasulka
   entrant of that tournament (confidence `confirmed`) or — for country-only
   tournaments — matches the season roster (confidence `roster-inferred`,
   shown with a ° marker on the page).

Output: `data/_fulldata.json` with `tournaments` (all, with entrants and
mode), `results` (per-tournament Tervasulka podium hits) and `roster`.

## Step 3 — ranking points

`step3_rankings.py` works in two phases against the pinned ranking publication:

1. **Discover member ids.** Reads the *club-filtered* ranking pages of the
   aggregate categories (open M/W singles/doubles/mixed, Juniorit, Seniorit —
   `ID_CATEGORIES`) and collects every Tervasulka member id. The category
   pages are **paginated**; every page is walked (`p=<n>&ps=100`) — reading
   only page 1 silently loses everyone ranked below the page break.
2. **Read each player's ranking page**
   (`/ranking/player.aspx?id=<publication>&player=<member>`), which itemises
   every counted result as (tournament, class, week, placing, points). Rows
   are de-duplicated (the same result appears once per class list it counts
   toward), filtered to **this season only** — ISO weeks 2025-W33 … 2026-W26,
   because the official ranking total uses a rolling window that mixes in the
   previous season — and aggregated per tournament.

Output: `data/_rankings.json` keyed by player name, with per-tournament
points and event breakdowns, and each tournament linked back to the domestic
calendar via the `(normalised name, ISO week)` key.

## Step 3b — cross-check against the per-tournament points pages

`step3b_crosscheck.py` exists because step 3 alone can miss awarded points: a
player's ranking page can be **empty** even though a tournament awarded them
points (observed 8/2026 — Ann Nelson had 1.5 pts on the Kumpoo Tervasulan
Eliitti 2026 page but a blank player page, and appeared in no club-filtered
category list, so discovery never found her). The per-tournament points page
(`/ranking/tournament.aspx?id=<publication>&tournament=<tid>`, tid from the
ranking tournament list) itemises every player's points per category at that
event and is treated as **authoritative**.

For every in-season tournament in the publication the step:

1. parses its points page into (category, member id, name, placing, points)
   rows;
2. identifies Tervasulka rows — by a member id already present in
   `_rankings.json`, or by token-name match against that tournament's
   confirmed TeSu entrants (from `_fulldata.json`);
3. compares each player's tournament total with `_rankings.json` and patches
   it in place: **missing players** and **missing tournaments** are added,
   **diverging totals** are replaced with the tournament-page events, and
   season totals are recomputed. Points present in `_rankings.json` but absent
   from the tournament page are only *reported* (never deleted).

Totals are compared with a per-event tolerance of 0.06 because player pages
round each event's points to one decimal (3.75 renders as `3,8`) while
tournament pages give exact values — without the tolerance every multi-event
player looks like a false mismatch.

Note the two sources label events differently (player page: `MD B`, `BS U13`;
tournament page: Finnish `MN B`, `MK U13`), so entries added by this step carry
the Finnish category labels. `division()` classifies both vocabularies.

## Step 4 — merge into the published dataset

`step4_build_dataset.py`:

1. **Filters to ranking tournaments** — `ranking_tournaments()` decides which
   tournaments (and their medals) survive; everything else is excluded from
   the published files.
2. **Builds canonical player identities** from the union of roster names,
   ranking names and medalist names, merged by token key (plus
   `NAME_ALIASES`). For each identity the display name is
   `DISPLAY_OVERRIDES` if set, otherwise the best-looking observed variant
   (prefers mixed case, no comma, most frequent).
3. **Attaches** participation (from entry lists), medals (from podium hits)
   and ranking points (from step 3) to each identity. Players left with no
   participation, no medals and no points after the filter are dropped.
4. **Writes** the four published files (schemas in `data/README.md`):
   - `players.json` — one record per player.
   - `tournaments.json` — the kept tournament catalogue.
   - `tervasulka_medals.json` — podium results grouped by tournament.
   - `tervasulka_medals.csv` — flat per-(player, medal) rows for Excel.

## Step 5 — render the page

`step5_build_html.py` renders the report page (into `Output/`) from the published JSON — a single
self-contained page (inline CSS/JS, inline club logo SVG) themed to match
tervasulka.fi. Four tabs:

- **Overview** — stat strip and medalist cards sorted by medal count.
- **Rankings** — every player, sorted by this-season ranking points, with a
  per-tournament points breakdown and links to official ranking pages.
- **Divisions** — every player with season points or a medal per division
  (`Valio/Elite`, A, B, C, Junior, …), ranked by season points earned *in that
  division's events*; non-medalists show an empty medal tally, so each player's
  division points sum to their Rankings-tab total. Medal-row names are folded
  onto canonical display names here, so a tournament that printed a name
  differently (e.g. all-caps) still lands on the right card.
- **Tournaments** — the kept tournament catalogue with entrant/medal counts.

A *Method & notes* section on the page states the coverage rules for readers.

## Caching

All fetched pages land in the season's cache directory `.cache/<season>/`
under stable names:

| Pattern | Contents |
|---------|----------|
| `tlist_page<n>.html` | tournament search result pages (step 1) |
| `<gid>_players.html`, `<gid>_winners.html` | entry list / winners page per tournament (step 2) |
| `<gid>_events.html`, `<gid>_event<n>.html` | event index / per-event entry pages, TeSu-connected tournaments only (step 2) |
| `rkcat_<publication>_<category>_p<page>.html` | club-filtered ranking category pages (step 3) |
| `rank_<publication>_<member>.html` | per-player ranking pages (step 3) |
| `rktournaments_<publication>.html` | the official ranking tournament list (steps 3b, 4) |
| `rktour_<publication>_<tid>.html` | per-tournament ranking points pages (step 3b) |

A cached file is used as-is when present. All ranking caches embed the
publication id, so bumping the ongoing season's publication refetches them
automatically — no manual deletion needed. `refresh.py` additionally drops the
volatile caches (search pages, unsettled tournaments; see *Maintenance*). To
force anything else, delete the relevant files (or the whole season dir) and
re-run.

## Maintenance

**Monthly refresh of the ongoing season** (new tournaments played, new results
processed by the federation):

```
cd src
py refresh.py
```

It detects the current publication id from `/ranking/`, validates the
configured category ids against that page (abort on mismatch; `--force`
overrides), stamps `publication` and `generated` into `seasons.json`, deletes
the volatile caches (tournament-search pages, and the per-tournament pages of
tournaments that don't yet have published results at least 14 days old), runs
steps 1–5, re-renders every finished season's page so the season-switcher
navigation stays consistent, and rebuilds `Output/tervasulka-report.html` — the
single-file share variant containing every season (its season dropdown
switches in-page, so the one file works standalone; also buildable alone with
`py build_share.py`). It warns if the player count drops sharply (the symptom
of stale category ids in step 3).

**Add a name alias** (same player appearing under two spellings): add the
token-key mapping to `NAME_ALIASES` in `src/twlib.py` (and
`DISPLAY_OVERRIDES` if the preferred display name needs forcing), then re-run
steps 4–5. A fuzzy duplicate scan that has proven useful: compare all pairs of
`players.json` names with `difflib.SequenceMatcher`, flag ratio > 0.75 with the
same first token. **Alias fixes apply forward only**: re-running steps 4–5 for
a `final` season deliberately changes a frozen page — do it consciously or not
at all.

**New season** (in `src/seasons.json`):

1. Flip the finished season's entry to `"status": "final"` (leave its
   `publication` and `generated` untouched — they freeze the page).
2. Append the new season's entry: `season`/`label`, `start`/`end` dates,
   `week_start`/`week_end` ISO-week window, `"publication": null`,
   `"generated": null`, `"status": "ongoing"`, and copy `categories` (verify
   the ids still exist on the new publication — `refresh.py` checks this).
3. `cd src && py refresh.py` — fills the publication, builds
   `data/<season>/`, writes the new `Output/index.html` and re-renders the old
   season as `<season>.html`.

## Pitfalls learned the hard way

- **Ranking category pages are paginated** (default 25 rows). Reading only
  page 1 silently drops every player below the fold — walk all pages.
- **A ranking publication is a frozen snapshot.** Re-fetching the same id
  never brings new data; the ongoing season's id must be bumped to refresh
  (`refresh.py` does this). The flip side makes archiving work: a finished
  season keeps its pinned id and never changes.
- **The same player appears under multiple spellings** across entry lists,
  winners pages and the ranking (case, transliteration, initials,
  `Last, First` vs `First Last`). Token-set matching handles ordering and
  case; genuine spelling differences need a `NAME_ALIASES` entry.
- **Winners pages print names as the tournament organiser typed them**
  (e.g. `Nelly MÄÄTTÄ`); fold them onto canonical names before grouping.
- **Not every tournament awards ranking points.** The authority is the
  publication's tournament list (`/ranking/tournaments.aspx?id=…`), which the
  pipeline now enforces. A player with a podium but no points either played a
  non-ranking event (now excluded) or won no matches (0 points is correct —
  the ranking awards nothing without a win/placing).
- **Matching tournaments by name needs normalisation** — ranking rows and the
  calendar differ in parentheticals/years; match on
  `(normalised name, ISO week of start date)`.
- **A player's ranking page can be empty even though they earned points.**
  Seen 8/2026 (Ann Nelson, 1.5 pts at Kumpoo Tervasulan Eliitti 2026): blank
  player page, absent from every club-filtered category list, but present on
  the tournament's points page. The per-tournament points pages are the
  authority — step 3b reconciles against them.
- **Player pages under-report when the class cell is blank.** International /
  junior-circuit rows carry no class label, so two different events with the
  same placing and points become identical rows and step 3's de-duplication
  (needed for real duplicates) collapses them. Step 3b restores the correct
  totals from the tournament pages.
- **The tournament-wide entry list includes players who never played.** A
  registration can end on an event's *Exclude list* or *Reserve list* (seen
  8/2026: Mikko Korkiakoski, Exclude list of XD C, Kumpoo Tervasulan Eliitti
  2026 — his only event, yet the entry list showed him as an entrant). Check
  each event page's entry rows (`elt9998`/`elt9999` = benched) and count only
  players who sit in at least one real draw. No-shows *do* count as
  participation — in the draw, zero points.
- **Never credit ranking rows by name alone.** Member id is the identity; an
  unrelated elite player named identically to a TeSu member would otherwise
  absorb ~19k points (seen 8/2026). Name-matching is only trusted for
  confirmed TeSu entrants of that specific tournament, and only when it does
  not contradict a known member id.
