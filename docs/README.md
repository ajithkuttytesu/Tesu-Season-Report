# Tervasulka Season Report — build documentation

How the Tervasulka 2025–26 season report (`index.html`) and its dataset
(`data/*.json`, `data/*.csv`) are built from
**badmintonfinland.tournamentsoftware.com**.

Last updated: 2026-08-09.

## Overview

The build is a six-step Python pipeline in `src/`. Each step reads the output
of the previous one and writes into `data/`; the final step renders the
self-contained report page `index.html` at the repository root.

```
tournamentsoftware.com
        │
        ▼
step1_list_tournaments.py   → data/tournaments_raw.tsv     (all season events)
        ▼
step2_entries_winners.py    → data/_fulldata.json          (entries, roster, podiums)
        ▼
step3_rankings.py           → data/_rankings.json          (ranking points per player)
        ▼
step3b_crosscheck.py        → data/_rankings.json          (verified/patched against
        ▼                                                   per-tournament points pages)
step4_build_dataset.py      → data/players.json, tournaments.json,
                              tervasulka_medals.json, tervasulka_medals.csv
        ▼
step5_build_html.py         → index.html                   (the report page)
```

Run everything with:

```
cd src
py run_all.py          # or run the steps individually: py step1_... etc.
```

Every HTTP fetch is cached on disk in `.cache/` (see *Caching* below), so
re-runs are fast and only fetch what is missing.

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
  - `RANKING_PUBLICATION` — the weekly ranking publication id everything is
    pinned to (currently `53055`, the latest at the last refresh). **A
    publication is a fixed snapshot**: re-fetching the same id returns the same
    data, so refreshing means bumping this id (see *Maintenance*).
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

`step5_build_html.py` renders `index.html` from the published JSON — a single
self-contained page (inline CSS/JS, inline club logo SVG) themed to match
tervasulka.fi. Four tabs:

- **Overview** — stat strip and medalist cards sorted by medal count.
- **Rankings** — every player, sorted by this-season ranking points, with a
  per-tournament points breakdown and links to official ranking pages.
- **Divisions** — medalists per division (`Valio/Elite`, A, B, C, Junior, …),
  ranked by season points earned *in that division's events*. Medal-row names
  are folded onto canonical display names here, so a tournament that printed
  a name differently (e.g. all-caps) still lands on the right card.
- **Tournaments** — the kept tournament catalogue with entrant/medal counts.

A *Method & notes* section on the page states the coverage rules for readers.

## Caching

All fetched pages land in `.cache/` under stable names:

| Pattern | Contents |
|---------|----------|
| `tlist_page<n>.html` | tournament search result pages (step 1) |
| `<gid>_players.html`, `<gid>_winners.html` | entry list / winners page per tournament (step 2) |
| `<gid>_events.html`, `<gid>_event<n>.html` | event index / per-event entry pages, TeSu-connected tournaments only (step 2) |
| `rkcat_<category>_p<page>.html` | club-filtered ranking category pages (step 3) |
| `rank_<member>.html` | per-player ranking pages (step 3) |
| `rktournaments_<publication>.html` | the official ranking tournament list (steps 3b, 4) |
| `rktour_<tid>.html` | per-tournament ranking points pages (step 3b) |

A cached file is used as-is when present. To force a refresh, delete the
relevant files (or all of `.cache/`) and re-run.

## Maintenance

**Refresh ranking data** (new results processed by the federation):

1. Find the current publication id: `https://badmintonfinland.tournamentsoftware.com/ranking/`
   redirects to `ranking.aspx?id=<current>`.
2. Set `RANKING_PUBLICATION` in `src/twlib.py`.
3. Delete `.cache/rank_*.html`, `.cache/rkcat_*.html`, `.cache/rktour_*.html`
   and `.cache/rktournaments_*.html`.
4. `py step3_rankings.py && py step3b_crosscheck.py && py step4_build_dataset.py
   && py step5_build_html.py`, and update `GEN` in `step5_build_html.py`.

**Add a name alias** (same player appearing under two spellings): add the
token-key mapping to `NAME_ALIASES` in `src/twlib.py` (and
`DISPLAY_OVERRIDES` if the preferred display name needs forcing), then re-run
steps 4–5. A fuzzy duplicate scan that has proven useful: compare all pairs of
`players.json` names with `difflib.SequenceMatcher`, flag ratio > 0.75 with the
same first token.

**New season**: update `SEASON_START`/`SEASON_END` in step 1, the
`in_season()` week window in step 3, `GEN` and page texts in step 5, then
clear `.cache/` and run `py run_all.py`.

## Pitfalls learned the hard way

- **Ranking category pages are paginated** (default 25 rows). Reading only
  page 1 silently drops every player below the fold — walk all pages.
- **A ranking publication is a frozen snapshot.** Re-fetching the same id
  never brings new data; bump `RANKING_PUBLICATION` to refresh.
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
