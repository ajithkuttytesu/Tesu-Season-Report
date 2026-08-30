"""Step 3b — cross-check ranking points against the per-tournament pages.

Step 3 collects season points from each player's ranking page, but that page
can be empty even when points were awarded (seen 8/2026: a player with points
on a tournament page had a blank player page and appeared in no club-filtered
category list, so step 3 missed her entirely).  The per-tournament points page
(/ranking/tournament.aspx?id=<pub>&tournament=<tid>) itemises what every
player earned at that event and is authoritative.

For every in-season tournament in the ranking publication this step:
  1. parses its points page,
  2. identifies Tervasulka rows — by member id already known from step 3, or
     by name-match against that tournament's confirmed TeSu entrants,
  3. compares per-player totals with data/_rankings.json and patches it:
     missing players and missing tournaments are added, diverging totals are
     replaced with the tournament-page events.

Totals are compared with a per-event tolerance because player pages display
points rounded to one decimal (3.75 shows as 3,8) while tournament pages give
exact values.  Divergence in the other direction (points in _rankings.json
that the tournament page does not show) is reported but never deleted.
"""
import os, json, sys
import twlib as T
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    rk_path = os.path.join(T.DATA, "_rankings.json")
    ranks = json.load(open(rk_path, encoding="utf-8"))
    full = json.load(open(os.path.join(T.DATA, "_fulldata.json"), encoding="utf-8"))

    # catalogue tournament + its confirmed TeSu participant name-keys, by (norm name, week)
    roster_keys = {T.tokens(nm) for nm in full["roster"]} | {T.tokens(nm) for nm in ranks}
    catalog = {}
    for t in full["tournaments"]:
        if t["clubmode"]:
            parts = {T.tokens(nm) for nm in t["terva_entrants"]}
        else:
            parts = {T.tokens(nm) for nm in t["all_entry_names"] if T.tokens(nm) in roster_keys}
        catalog[(T.norm_tname(t["name"]), T.isoweek(t["date"]))] = (t, parts)

    by_mid = {rec["member_id"]: name for name, rec in ranks.items()}
    by_key = {T.tokens(name): name for name in ranks}

    def find_entry(rec, tname, week):
        for e in rec["tournaments"]:
            if e["week"] == week and T.norm_tname(e["tournament"]) == T.norm_tname(tname):
                return e
        return None

    season = [t for t in T.ranking_tournament_index() if T.in_season(t["week"])]
    n_rows = n_ok = 0
    added_players, added_tours, fixed, warns = [], [], [], []
    touched = set()

    for tour in season:
        key = (T.norm_tname(tour["name"]), tour["week"])
        cat = catalog.get(key)
        page = {}
        for r in T.ranking_tournament_points(tour["tid"]):
            page.setdefault(r["member_id"], []).append(r)

        seen_mids = set()
        for mid, rows in page.items():
            name = rows[0]["name"]
            known = by_mid.get(mid)
            if not known:
                # A name-only match is trusted only for a confirmed TeSu entrant
                # of THIS tournament; member id is the real identity — the same
                # name with a different id is a different person (seen 8/2026:
                # a non-TeSu 'Tommi Kaikkonen' nearly credited 19k elite points
                # to the TeSu player of the same name).
                if not (cat and T.tokens(name) in cat[1]):
                    continue                   # not a Tervasulka player
                clash = by_key.get(T.tokens(name))
                if clash and ranks[clash]["member_id"] != mid:
                    warns.append(f"{name} on {tour['name']} page has member id {mid}, "
                                 f"but TeSu {clash} is {ranks[clash]['member_id']} — "
                                 f"treated as a different player, not credited")
                    continue
            n_rows += len(rows)
            seen_mids.add(mid)
            total = sum(r["points"] for r in rows)
            entry = dict(
                tournament=tour["name"],
                date=cat[0]["date"] if cat else "",
                week=tour["week"],
                url=T.tournament_url(cat[0]["gid"]) if cat else "",
                points=round(total, 1),
                events=[dict(event=r["category"], placing=r["placing"],
                             points=round(r["points"], 1))
                        for r in sorted(rows, key=lambda r: -r["points"])])
            if not known:                      # step 3 missed this player entirely
                ranks[name] = dict(member_id=mid, url=T.ranking_player_url(mid),
                                   season_points=0.0, tournaments=[entry])
                by_mid[mid], by_key[T.tokens(name)] = name, name
                touched.add(name)
                added_players.append(f"{name} ({mid}): {tour['name']} +{entry['points']:g}")
                continue
            rec = ranks[known]
            old = find_entry(rec, tour["name"], tour["week"])
            if old is None:                    # player known, this tournament missing
                rec["tournaments"].append(entry)
                touched.add(known)
                added_tours.append(f"{known}: {tour['name']} +{entry['points']:g}")
            elif abs(old["points"] - total) > 0.06 * max(1, len(rows)):
                fixed.append(f"{known}: {tour['name']} {old['points']:g} -> {entry['points']:g}")
                old["points"], old["events"] = entry["points"], entry["events"]
                touched.add(known)
            else:
                n_ok += 1

        # reverse direction: season points recorded for this tournament, but the
        # tournament page shows nothing for that member id
        for name, rec in ranks.items():
            if name in touched or rec["member_id"] in seen_mids:
                continue
            e = find_entry(rec, tour["name"], tour["week"])
            if e:
                warns.append(f"{name}: {e['points']:g} pts for {tour['name']} in "
                             f"_rankings.json but not on its ranking page")

    for name in touched:
        rec = ranks[name]
        rec["tournaments"].sort(key=lambda x: (x["date"] or f"wk{T.week_key(x['week']):06d}"))
        rec["season_points"] = round(sum(t["points"] for t in rec["tournaments"]), 1)

    ranks = dict(sorted(ranks.items(), key=lambda kv: -kv[1]["season_points"]))
    json.dump(ranks, open(rk_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"step3b: cross-checked {len(season)} tournament ranking pages, "
          f"{n_rows} Tervasulka point rows, {n_ok} player-tournament totals verified")
    for label, items in (("added missing player", added_players),
                         ("added missing tournament", added_tours),
                         ("corrected points", fixed), ("WARNING", warns)):
        for it in items:
            print(f"  {label}: {it}")
    if not (added_players or added_tours or fixed or warns):
        print("  no discrepancies found")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", help="season key from seasons.json, default: ongoing")
    T.configure(ap.parse_args().season)
    run()
