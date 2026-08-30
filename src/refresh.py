"""Monthly refresh of the ongoing season.

    py refresh.py [--force]

1. Detects the current weekly ranking publication id from /ranking/ (the site
   redirects to ranking.aspx?id=<current>).
2. Validates the configured member-id category ids against the ranking page and
   aborts if any is missing (a wrong id silently loses players in step 3);
   --force overrides.
3. Stamps the ongoing season's publication + generated date into seasons.json.
4. Invalidates volatile caches: tournament-search pages, and per-tournament
   pages of tournaments that are not yet settled (no published results, or too
   recent).  Ranking caches are publication-qualified, so a publication bump
   refetches them automatically; stale-publication files are pruned.
5. Runs pipeline steps 1-5 for the ongoing season.
6. Re-renders every finished season's page (from its frozen data, no network)
   so the season-switcher navigation stays consistent on all pages.
"""
import argparse, datetime, glob, json, os, re, sys
import twlib as T
import step1_list_tournaments, step2_entries_winners, step3_rankings
import step3b_crosscheck, step4_build_dataset, step5_build_html
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SETTLED_AGE_DAYS = 14   # a tournament with published results this old won't change


def detect_publication():
    """Current publication id: /ranking/ redirects to ranking.aspx?id=<id>."""
    T._ensure_session()
    r = T._opener.open(T.BASE + "/ranking/", timeout=40)
    body = r.read().decode("utf-8", "ignore")
    m = (re.search(r"[?&]id=(\d+)", r.geturl())
         or re.search(r"ranking\.aspx\?id=(\d+)", body))
    if not m:
        raise SystemExit("refresh: could not detect the current ranking "
                         "publication id from /ranking/")
    return m.group(1), body


def check_categories(season, body, force):
    """Warn/abort when a configured category id is absent from the ranking page."""
    found = set(re.findall(r"category\.aspx\?id=\d+&(?:amp;)?category=(\d+)", body))
    if not found:
        print("refresh: WARNING - no category ids found on the ranking page; "
              "cannot validate seasons.json categories (see post-run sanity check)")
        return
    missing = [c for c in season["categories"] if c not in found]
    if missing:
        labels = ", ".join(f"{c} ({season['categories'][c]})" for c in missing)
        print(f"refresh: configured category ids missing from the ranking page: {labels}")
        print(f"refresh: ids on the page: {', '.join(sorted(found, key=int))}")
        if not force:
            raise SystemExit("refresh: fix the ongoing season's categories in "
                             "seasons.json (or re-run with --force)")
        print("refresh: --force given, continuing with the configured ids")


def invalidate_caches(pub):
    """Drop caches that can change between refreshes (in the season's cache dir)."""
    removed = 0
    # tournament-search results grow all season
    for f in glob.glob(os.path.join(T.CACHE, "tlist_page*.html")):
        os.remove(f); removed += 1
    # per-tournament pages of unsettled tournaments (entry lists churn before the
    # event; winners appear only after it); settled = published results + old
    settled = set()
    full_path = os.path.join(T.DATA, "_fulldata.json")
    if os.path.exists(full_path):
        cutoff = (datetime.date.today() - datetime.timedelta(days=SETTLED_AGE_DAYS)).isoformat()
        full = json.load(open(full_path, encoding="utf-8"))
        settled = {t["gid"].lower() for t in full["tournaments"]
                   if t["has_results"] and t["date"] and t["date"] <= cutoff}
    for f in glob.glob(os.path.join(T.CACHE, "*_*.html")):
        name = os.path.basename(f)
        m = re.match(r"([0-9a-fA-F-]{36})_", name)
        if m and m.group(1).lower() not in settled:
            os.remove(f); removed += 1
    # prune ranking caches of other publications (current ones are pub-qualified)
    for pat in ("rank_*.html", "rkcat_*.html", "rktour_*.html", "rktournaments_*.html"):
        for f in glob.glob(os.path.join(T.CACHE, pat)):
            pm = re.match(r"(?:rank|rkcat|rktour|rktournaments)_(\d+)", os.path.basename(f))
            if pm and pm.group(1) != pub:
                os.remove(f); removed += 1
    print(f"refresh: invalidated {removed} cached pages "
          f"({len(settled)} settled tournaments kept)")


def run(force=False):
    season = T.configure()
    print(f"refresh: ongoing season {season['season']}")

    pub, body = detect_publication()
    print(f"refresh: current ranking publication {pub}"
          + ("" if pub != season["publication"] else " (unchanged)"))
    check_categories(season, body, force)

    # stamp registry and reconfigure so the pipeline sees the new publication
    seasons = T.load_seasons()
    for s in seasons:
        if s["season"] == season["season"]:
            s["publication"] = pub
            s["generated"] = datetime.date.today().isoformat()
    T.save_seasons(seasons)
    season = T.configure()

    prev_players = None
    pj = os.path.join(T.DATA, "players.json")
    if os.path.exists(pj):
        prev_players = len(json.load(open(pj, encoding="utf-8")))

    invalidate_caches(pub)

    step1_list_tournaments.run()
    step2_entries_winners.run()
    step3_rankings.run()
    step3b_crosscheck.run()
    step4_build_dataset.run()
    step5_build_html.run()

    # keep archived pages' season navigation in sync (frozen data, no network)
    for s in T.load_seasons():
        if s["status"] == "final":
            T.configure(s["season"])
            step5_build_html.run()
    # single-file variant with all seasons, for sharing
    import build_share
    build_share.run()
    T.configure()

    players = json.load(open(pj, encoding="utf-8"))
    print(f"\nrefresh: done — publication {pub}, {len(players)} players, "
          f"{sum(p['total_medals'] for p in players)} medals")
    if prev_players and len(players) < prev_players * 0.8:
        print(f"refresh: WARNING - player count dropped {prev_players} -> {len(players)}; "
              f"check the category ids in seasons.json (step 3 may be losing players)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="continue even if configured category ids are missing")
    run(force=ap.parse_args().force)
