"""Step 3 — Tervasulka ranking points, per player and per tournament.

Two phases:
  1. Discover every Tervasulka ranking member id by reading the club-filtered
     ranking for the OPEN, JUNIORIT and SENIORIT aggregate categories of each
     discipline (so junior-only and senior-only players are included).
  2. For each member id, read the player's ranking page, which itemises every
     result as (tournament, class, week, placing, points).  We dedupe, keep only
     THIS SEASON's results (by ISO week), and aggregate per tournament.

The official ranking total uses a rolling window, so it mixes in
previous-season results; here we count only the configured season's tournaments
(ISO-week window and category ids come from seasons.json via twlib).

Writes data/<season>/_rankings.json keyed by player name.
"""
import os, re, json, sys
import twlib as T
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def discover_member_ids():
    found = {}   # member_id -> name
    for cid in T.ID_CATEGORIES:
        page = 1
        while True:          # category lists are paginated; walk every page
            doc = T.fetch(f"/ranking/category.aspx?id={T.RANKING_PUBLICATION}"
                          f"&category={cid}&ogid={T.TERVA_RANKING_OGID}&p={page}&ps=100",
                          cache_name=f"rkcat_{T.RANKING_PUBLICATION}_{cid}_p{page}.html")
            hits = re.findall(r'player\.aspx\?id=\d+&player=(\d+)">([^<]+)</a>', doc)
            for mid, nm in hits:
                found[mid] = T.unesc(nm)
            if not hits or not re.search(rf'[?&](?:amp;)?p={page + 1}&(?:amp;)?ps=', doc):
                break
            page += 1
    return found

def parse_player_results(member_id):
    doc = T.fetch(f"/ranking/player.aspx?id={T.RANKING_PUBLICATION}&player={member_id}",
                  cache_name=f"rank_{T.RANKING_PUBLICATION}_{member_id}.html")
    flat = re.sub(r"\s+", " ", doc)
    out, seen = [], set()
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", flat):
        cells = [T.unesc(re.sub(r"<[^>]+>", "", c)) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr)]
        if len(cells) >= 5 and re.match(r"20\d\d-\d{1,2}$", cells[2]) and re.match(r"[\d ]+,\d$", cells[4]):
            tournament, cls, week, placing, pts = cells[0], cells[1], cells[2], cells[3], cells[4]
            key = (tournament, cls, week, placing, pts)
            if key in seen:
                continue
            seen.add(key)
            out.append(dict(tournament=tournament, cls=cls, week=week, placing=placing,
                            points=float(pts.replace(" ", "").replace(",", "."))))
    return out

import datetime
def _norm(n):
    n = re.sub(r"\(.*?\)", "", n)          # drop parentheticals
    n = re.sub(r"\b20\d\d\b", "", n)        # drop year
    return re.sub(r"\s+", " ", n).strip().lower()
def _isoweek(date):
    y, w, _ = datetime.date.fromisoformat(date).isocalendar()
    return f"{y}-{w}"

def run():
    # catalogue: exact-name and (normalised-name, iso-week) -> date/url
    raw = os.path.join(T.DATA, "tournaments_raw.tsv")
    catalog, catalog_nw = {}, {}
    if os.path.exists(raw):
        for line in open(raw, encoding="utf-8"):
            date, gid, name, loc = line.rstrip("\n").split("\t")
            url = T.tournament_url(gid)
            catalog[name.lower()] = (date, url)
            catalog_nw[(_norm(name), _isoweek(date))] = (date, url)

    def lookup(tname, week):
        if tname.lower() in catalog:
            return catalog[tname.lower()]
        return catalog_nw.get((_norm(tname), week), ("", ""))

    members = discover_member_ids()
    players = {}
    for mid, name in members.items():
        rows = [r for r in parse_player_results(mid) if T.in_season(r["week"])]
        if not rows:
            continue
        per_t = {}
        for r in rows:
            t = per_t.setdefault(r["tournament"], dict(points=0.0, events=[], week=r["week"]))
            t["points"] += r["points"]
            t["events"].append(dict(event=r["cls"], placing=r["placing"], points=round(r["points"], 1)))
        tours = []
        for tname, info in per_t.items():
            date, url = lookup(tname, info["week"])
            tours.append(dict(tournament=tname, date=date, week=info["week"], url=url,
                              points=round(info["points"], 1),
                              events=sorted(info["events"], key=lambda e: -e["points"])))
        tours.sort(key=lambda x: (x["date"] or f"wk{T.week_key(x['week']):06d}"))
        players[name] = dict(
            member_id=mid, url=T.ranking_player_url(mid),
            season_points=round(sum(t["points"] for t in tours), 1),
            tournaments=tours)

    players = dict(sorted(players.items(), key=lambda kv: -kv[1]["season_points"]))
    json.dump(players, open(os.path.join(T.DATA, "_rankings.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"step3: {len(members)} member ids, {len(players)} players with season ranking points "
          f"-> data/_rankings.json")

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", help="season key from seasons.json, default: ongoing")
    T.configure(ap.parse_args().season)
    run()
