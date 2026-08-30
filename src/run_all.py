"""Run the whole pipeline end-to-end: steps 1-5.

    python run_all.py [--season 2025-26]

Defaults to the ongoing season from seasons.json.  Uses the per-season on-disk
cache in ../.cache/<season> when present, so re-runs are fast and only missing
pages are fetched.  For the monthly refresh of the ongoing season prefer
refresh.py, which also detects the current ranking publication and invalidates
stale caches.
"""
import argparse
import twlib as T
import step1_list_tournaments, step2_entries_winners, step3_rankings
import step3b_crosscheck, step4_build_dataset, step5_build_html

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", help="season key from seasons.json, default: ongoing")
    season = T.configure(ap.parse_args().season)
    step1_list_tournaments.run()
    step2_entries_winners.run()
    step3_rankings.run()
    step3b_crosscheck.run()
    step4_build_dataset.run()
    step5_build_html.run()
    page = "index.html" if season["status"] == "ongoing" else f"{season['season']}.html"
    print(f"\nDone. Open ../Output/{page}")
