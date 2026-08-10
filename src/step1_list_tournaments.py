"""Step 1 — enumerate every badminton tournament of the 2025-26 season.

Pages through the site's tournament search (SportID=2) for the season date
range and writes data/tournaments_raw.tsv  (date<TAB>guid<TAB>name<TAB>location).
"""
import os, re, html, sys
import twlib as T
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SEASON_START = "2025-08-01T00:00"
SEASON_END   = "2026-06-30T00:00"

def run():
    # The DoSearch endpoint returns cumulative results; page until it stops growing.
    seen = {}
    prev = -1
    for page in range(1, 20):
        body = {
            "Page": str(page),
            "TournamentExtendedFilter.SportID": "2",
            "TournamentFilter.Q": "",
            "TournamentFilter.DateFilterType": "0",
            "TournamentFilter.StartDate": SEASON_START,
            "TournamentFilter.EndDate": SEASON_END,
        }
        h = T.fetch("/find/tournament/DoSearch", cache_name=f"tlist_page{page}.html",
                    xhr=True, post=body)
        for it in re.split(r'<li class="list__item">', h):
            m = re.search(r'/sport/tournament\?id=([A-F0-9-]+)', it)
            if not m:
                continue
            gid = m.group(1)
            t = re.search(r'<a [^>]*title="([^"]+)"[^>]*class="media__link"', it)
            d = re.search(r'datetime="([0-9-]+)', it)
            loc = re.search(r'icon-marker.*?nav-link__value">\s*([^<]+?)\s*</span>', it, re.S)
            seen[gid] = (d.group(1) if d else "",
                         T.unesc(t.group(1)) if t else "",
                         T.unesc(loc.group(1)) if loc else "")
        if len(seen) == prev:
            break
        prev = len(seen)

    rows = sorted(((v[0], g, v[1], v[2]) for g, v in seen.items()))
    out = os.path.join(T.DATA, "tournaments_raw.tsv")
    with open(out, "w", encoding="utf-8") as f:
        for date, gid, name, loc in rows:
            f.write(f"{date}\t{gid}\t{name}\t{loc}\n")
    print(f"step1: {len(rows)} tournaments -> {out}")

if __name__ == "__main__":
    run()
