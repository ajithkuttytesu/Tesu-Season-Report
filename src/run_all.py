"""Run the whole pipeline end-to-end: steps 1-5.

    python run_all.py

Uses the on-disk cache in ../.cache when present, so re-runs are fast and only
missing pages are fetched. Delete ../.cache to force a full refresh.
"""
import step1_list_tournaments, step2_entries_winners, step3_rankings
import step3b_crosscheck, step4_build_dataset, step5_build_html

if __name__ == "__main__":
    step1_list_tournaments.run()
    step2_entries_winners.run()
    step3_rankings.run()
    step3b_crosscheck.run()
    step4_build_dataset.run()
    step5_build_html.run()
    print("\nDone. Open ../index.html")
