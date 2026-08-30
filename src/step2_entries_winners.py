"""Step 2 — for every tournament, read the entry list and the winners page.

Entry list (/tournament/<id>/Players/GetPlayersContent) gives each entrant and,
when the tournament exposes it, their club.  Some tournaments show only
nationality; those are flagged 'country' mode.  Winners page
(/sport/winners.aspx) gives the podium placings per event.

The entry list includes players who registered but never played: each event's
page (/sport/event.aspx?id=<gid>&event=<n>) labels entries as Maindraw /
Reserve list / Exclude list.  A player whose every event entry is on the
reserve or exclude list did not participate and is removed from the
tournament's entrant lists (no-shows stay: they are in a real draw, they just
earned no points).  Event pages are only fetched for tournaments with a
Tervasulka connection.

Writes data/_fulldata.json with: tournaments (all, with entrants + mode) and
results (per tournament: hits = Tervasulka podium finishes).
"""
import os, re, json, sys
import twlib as T
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def parse_players(gid):
    g = gid.lower()
    doc = T.fetch(f"/tournament/{g}/Players/GetPlayersContent",
                  cache_name=f"{g}_players.html", xhr=True)
    rows = []
    for li in re.split(r'<li class="list__item js-alphabet-list-item"', doc):
        nm = re.search(r'class="nav-link media__link"><span class="nav-link__value">([^<]+)</span>', li)
        if not nm:
            continue
        subs = [T.unesc(x) for x in re.findall(
            r'media__subheading">\s*<span class="nav-link[^"]*"><span class="nav-link__value">([^<]+)</span>', li)]
        clubs = [s for s in subs if not T.is_country(s)]
        rows.append((T.unesc(nm.group(1)), clubs))
    return rows

def _row_names(tr):
    """Player names in one entries-table row ('[FIN] Mikko Korkiakoski' -> tokens)."""
    out = []
    for a in re.findall(r'player\.aspx\?id=[^"]*&(?:amp;)?player=\d+"[^>]*>(.*?)</a>', tr):
        nm = T.unesc(re.sub(r"<[^>]+>", "", a))
        nm = re.sub(r"^\[[A-Z]{2,3}\]\s*", "", nm).strip()
        if nm:
            out.append(T.tokens(nm))
    return out

def scan_event_lists(gid):
    """Token-keys of players in a real draw vs. only benched (reserve/exclude).

    Walks every event page of the tournament.  Entry rows carry a status cell:
    class elt9999 = Exclude list, elt9998 = Reserve list, anything else
    (Maindraw, qualification, ...) is a real draw.  Returns (indraw, benched);
    both empty when the tournament publishes no event entry tables."""
    g = gid.lower()
    doc = T.fetch(f"/sport/events.aspx?id={g}", cache_name=f"{g}_events.html")
    eids = list(dict.fromkeys(re.findall(r'event\.aspx\?id=[^"&]*&(?:amp;)?event=(\d+)"', doc)))
    indraw, benched = set(), set()
    for eid in eids:
        ev = T.fetch(f"/sport/event.aspx?id={g}&event={eid}", cache_name=f"{g}_event{eid}.html")
        flat = re.sub(r"\s+", " ", ev)
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", flat):
            m = re.search(r'<td class="[^"]*\belt(\d+)\b[^"]*">', tr)
            if not m:
                continue
            (benched if m.group(1) in ("9998", "9999") else indraw).update(_row_names(tr))
    return indraw, benched

def parse_winners(gid):
    g = gid.lower()
    doc = T.fetch(f"/sport/winners.aspx?id={g}", cache_name=f"{g}_winners.html")
    flat = re.sub(r"\s+", " ", doc)
    res, cur = [], None
    for row in re.split(r"<tr>", flat):
        m = re.search(r'event\.aspx\?id=[^"]*&event=[0-9]+">([^<]+)</a>', row)
        if m and "<th" in row:
            cur = T.unesc(m.group(1)); continue
        rk = re.search(r"<td>([0-9][0-9/]*)</td>", row)
        names = [T.unesc(x) for x in re.findall(r'player=[0-9]+">([^<]+)</a>', row)]
        if rk and cur and names:
            res.append((cur, rk.group(1), names))
    return res

def run():
    src = os.path.join(T.DATA, "tournaments_raw.tsv")
    tl = [l.rstrip("\n").split("\t") for l in open(src, encoding="utf-8")]

    # Pass 1: entries, club-mode classification, master Tervasulka roster from ENTRIES
    tours, master, appearances = [], {}, {}
    for date, gid, name, loc in tl:
        rows = parse_players(gid)
        clubmode = any(cl for _, cl in rows)
        terva = []
        for nm, cl in rows:
            if any(c.lower() in T.CLUB_NAMES for c in cl):
                terva.append(nm); k = T.tokens(nm); master[k] = nm
                appearances.setdefault(k, []).append([date, name])
        tours.append(dict(date=date, gid=gid, name=name, loc=loc, clubmode=clubmode,
                          n_players=len(rows), terva_entrants=sorted(terva),
                          all_entry_names=[nm for nm, _ in rows]))

    # Pass 1b: drop entrants who never made a real draw (exclude/reserve lists).
    # Only tournaments with a Tervasulka connection are scanned; when a
    # tournament publishes no event entry tables nothing is filtered.
    n_dropped = 0
    for t in tours:
        relevant = t["terva_entrants"] or (
            not t["clubmode"] and any(T.tokens(nm) in master for nm in t["all_entry_names"]))
        if not relevant:
            continue
        indraw, benched = scan_event_lists(t["gid"])
        drop = benched - indraw
        if not drop:
            continue
        gone = [nm for nm in t["terva_entrants"] if T.tokens(nm) in drop]
        for nm in gone:
            print(f"step2: {t['name']}: {nm} only on exclude/reserve list -> not a participant")
            k = T.tokens(nm)
            appearances[k] = [a for a in appearances.get(k, []) if a != [t["date"], t["name"]]]
        n_dropped += len(gone)
        t["terva_entrants"] = [nm for nm in t["terva_entrants"] if T.tokens(nm) not in drop]
        t["all_entry_names"] = [nm for nm in t["all_entry_names"] if T.tokens(nm) not in drop]

    # Pass 2: podium matching (club-mode -> entry list; country-mode -> roster)
    results = []
    for t in tours:
        pod = parse_winners(t["gid"])
        if t["clubmode"]:
            idset = set(T.tokens(x) for x in t["terva_entrants"]); confirmed = True
        else:
            idset = set(master.keys()); confirmed = False
        hits = []
        for ev, place, players in pod:
            if not T.is_medal(place):
                continue
            tv = [T.clean_name(p) for p in players if T.tokens(p) in idset]
            if tv:
                hits.append(dict(event=ev, place=place, medal=T.medal_name(place),
                                 terva_players=tv, partners=[T.clean_name(p) for p in players],
                                 confidence="confirmed" if confirmed else "roster-inferred",
                                 division=T.division(ev)))
        t["n_medals"] = len(hits); t["has_results"] = len(pod) > 0
        if t["terva_entrants"] or hits:
            results.append(dict(t, hits=hits))

    out = dict(tournaments=tours, results=results,
               roster={master[k]: appearances.get(k, []) for k in master})
    json.dump(out, open(os.path.join(T.DATA, "_fulldata.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"step2: {len(tours)} tournaments, {sum(1 for r in results if r['hits'])} with medals, "
          f"entry-roster {len(master)} players, {n_dropped} exclude/reserve-only entries dropped "
          f"-> data/_fulldata.json")

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", help="season key from seasons.json, default: ongoing")
    T.configure(ap.parse_args().season)
    run()
