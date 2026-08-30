"""Build a single self-contained HTML file with every season's report.

    py build_share.py

Writes ../Output/tervasulka-report.html — all seasons in one file, the season
dropdown switches between them in-page. Made for sharing (mail, chat, USB):
no other files or network needed. Rendered from the committed per-season
datasets; run refresh.py first to update the ongoing season.
"""
import os, sys
import twlib as T
import step5_build_html as S5
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_NAME = "tervasulka-report.html"

def run():
    seasons = sorted(T.load_seasons(), key=lambda s: s["season"], reverse=True)
    o = S5.page_head("Tervasulka — Season Reports")
    stats = []
    for i, s in enumerate(seasons):
        T.configure(s["season"])
        body, (n_pl, *_rest) = S5.build_body(share=True, hidden=(i > 0))
        o += body
        stats.append(f"{s['season']}: {n_pl} players")
    o.append("<script>" + S5.JS + "</script></body></html>")
    outdir = os.path.join(T.REPO, "Output")
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, OUT_NAME)
    open(out, "w", encoding="utf-8").write("\n".join(o))
    size = os.path.getsize(out) / 1024
    print(f"share: HTML -> {out}  ({size:.0f} kB; {'; '.join(stats)})")

if __name__ == "__main__":
    run()
