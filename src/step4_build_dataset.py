"""Step 4 — merge entries/winners (step2) with rankings (step3) into the
published data files under data/.

Outputs:
  players.json            per-player: tournaments played, medals, ranking points
  tournaments.json        catalogue of all scanned tournaments
  tervasulka_medals.json  podium results grouped by tournament
  tervasulka_medals.csv   flat one-row-per (player, medal)
"""
import os, re, json, csv, sys
from collections import defaultdict, Counter
import twlib as T
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def _flip(name):
    """'Last, First' -> 'First Last' so all display names read naturally."""
    if name.count(",") == 1:
        last, first = (s.strip() for s in name.split(","))
        if last and first:
            return f"{first} {last}"
    return name

def best_display(counter):
    def score(v):
        caps = sum(1 for t in v.split() if t.isupper() and len(t) > 1)
        return (caps, "," in v, -counter[v], -sum(c.islower() for c in v))
    return _flip(sorted(counter, key=score)[0])

def run():
    full = json.load(open(os.path.join(T.DATA, "_fulldata.json"), encoding="utf-8"))
    ranks = json.load(open(os.path.join(T.DATA, "_rankings.json"), encoding="utf-8"))
    tours, results, roster = full["tournaments"], full["results"], full["roster"]

    # ---- keep only tournaments on the official ranking list ----
    # Tournaments not in the ranking publication (local pool/school/club-internal
    # events) award no points; their results are excluded from the report.
    rk_keys = T.ranking_tournaments()
    def is_ranked(t):
        return (T.norm_tname(t["name"]), T.isoweek(t["date"])) in rk_keys
    n_all = len(tours)
    tours = [t for t in tours if is_ranked(t)]
    results = [r for r in results if is_ranked(r)]
    print(f"step4: ranking-list filter keeps {len(tours)}/{n_all} tournaments")

    # ---- canonical player identity (merge name variants by token set) ----
    name_variants = defaultdict(Counter)
    for nm in roster:                       # entry-confirmed Tervasulka players
        name_variants[T.tokens(nm)][nm] += 1
    for nm in ranks:                        # ranking-confirmed Tervasulka players
        name_variants[T.tokens(nm)][nm] += 1
    for r in results:                       # ensure medalist names are represented
        for h in r["hits"]:
            for p in h["terva_players"]:
                name_variants[T.tokens(p)][p] += 1
    known = set(name_variants)              # all Tervasulka identity keys

    rank_by_key = {T.tokens(nm): info for nm, info in ranks.items()}

    players = {}
    for key, variants in name_variants.items():
        players[key] = dict(
            name=T.DISPLAY_OVERRIDES.get(key) or best_display(variants),
            tournaments=[],                 # list of [date, name] entered
            gold=0, silver=0, bronze=0, medals=[],
            ranking=rank_by_key.get(key))

    # ---- participation from ENTRIES (club-confirmed + country-mode name match) ----
    for t in tours:
        if t["clubmode"]:
            for nm in t["terva_entrants"]:
                k = T.tokens(nm)
                if k in players:
                    players[k]["tournaments"].append([t["date"], t["name"]])
        else:
            for nm in t["all_entry_names"]:
                k = T.tokens(nm)
                if k in known and k in players:
                    players[k]["tournaments"].append([t["date"], t["name"]])

    # de-dup participation (a player can enter several events in one tournament)
    for p in players.values():
        seen, uniq = set(), []
        for d, n in sorted(p["tournaments"]):
            if (d, n) not in seen:
                seen.add((d, n)); uniq.append([d, n])
        p["tournaments"] = uniq

    # ---- medals from results ----
    midx = {"Gold": "gold", "Silver": "silver", "Bronze": "bronze"}
    for r in results:
        for h in r["hits"]:
            for p in h["terva_players"]:
                k = T.tokens(p)
                if k not in players:
                    continue
                players[k][midx[h["medal"]]] += 1
                partners = [x for x in h["partners"] if T.tokens(x) != k]
                players[k]["medals"].append(dict(
                    date=r["date"], tournament=r["name"], event=h["event"],
                    division=h["division"], medal=h["medal"], place=h["place"],
                    partners=partners, confidence=h["confidence"]))

    # ---- emit players.json ----
    # Players whose only appearances were at excluded (non-ranking) tournaments
    # have nothing left to show; drop them.
    plist = []
    for p in players.values():
        if not (p["tournaments"] or p["medals"] or p["ranking"]):
            continue
        rk = p["ranking"]
        plist.append(dict(
            name=p["name"],
            tournaments_played=len(p["tournaments"]),
            tournaments=p["tournaments"],
            gold=p["gold"], silver=p["silver"], bronze=p["bronze"],
            total_medals=p["gold"] + p["silver"] + p["bronze"],
            medals=sorted(p["medals"], key=lambda m: m["date"]),
            ranking_points=rk["season_points"] if rk else None,
            ranking_tournaments=rk["tournaments"] if rk else None,
            ranking_member_id=rk["member_id"] if rk else None,
            ranking_url=rk["url"] if rk else None))
    plist.sort(key=lambda p: (-(p["gold"]*100 + p["silver"]*10 + p["bronze"]),
                              -(p["ranking_points"] or 0), p["name"]))
    json.dump(plist, open(os.path.join(T.DATA, "players.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    # ---- tournaments.json ----
    cat = []
    for t in sorted(tours, key=lambda x: x["date"]):
        cat.append(dict(
            date=t["date"], name=t["name"], location=t["loc"],
            url=T.tournament_url(t["gid"]), winners_url=T.winners_url(t["gid"]),
            tournament_id=t["gid"],
            entry_list_shows="club" if t["clubmode"] else "country_only",
            players=t["n_players"], tervasulka_entrants=t["terva_entrants"],
            tervasulka_medals=t.get("n_medals", 0),
            has_published_results=t.get("has_results", False)))
    json.dump(cat, open(os.path.join(T.DATA, "tournaments.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    # ---- medals grouped by tournament ----
    med = []
    for r in sorted(results, key=lambda x: x["date"]):
        if not r["hits"]:
            continue
        med.append(dict(date=r["date"], tournament=r["name"], location=r["loc"],
                        tournament_id=r["gid"], url=T.winners_url(r["gid"]),
                        medals=[dict(event=h["event"], division=h["division"],
                                     place=h["place"], medal=h["medal"],
                                     tervasulka_players=h["terva_players"],
                                     all_players_in_entry=h["partners"],
                                     confidence=h["confidence"]) for h in r["hits"]]))
    json.dump(med, open(os.path.join(T.DATA, "tervasulka_medals.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    # ---- flat CSV ----
    with open(os.path.join(T.DATA, "tervasulka_medals.csv"), "w",
              encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "tournament", "location", "event", "division",
                    "place", "medal", "player", "partners", "confidence"])
        for r in sorted(results, key=lambda x: x["date"]):
            for h in r["hits"]:
                partners = [x for x in h["partners"] if x not in h["terva_players"]]
                for p in h["terva_players"]:
                    w.writerow([r["date"], r["name"], r["loc"], h["event"], h["division"],
                                h["place"], h["medal"], p, "; ".join(partners), h["confidence"]])

    print(f"step4: players.json ({len(plist)}), tournaments.json ({len(cat)}), "
          f"tervasulka_medals.json ({len(med)}), .csv")

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", help="season key from seasons.json, default: ongoing")
    T.configure(ap.parse_args().season)
    run()
