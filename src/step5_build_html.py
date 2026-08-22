"""Step 5 — build the tabbed HTML report from the data/*.json files."""
import os, json, html, sys
from collections import defaultdict
import twlib as T
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GEN = "2026-08-09"
M = {"Gold": "\U0001F947", "Silver": "\U0001F948", "Bronze": "\U0001F949"}
DIV_ORDER = ["Valio/Elite", "A", "B", "C", "D", "Junior", "Senior", "Other"]

def esc(s): return html.escape(str(s))
def fp(x):
    """Points for display: whole numbers plain, fractions with one decimal."""
    return f"{x:.0f}" if float(x) == int(x) else f"{x:.1f}"
def fd(d):
    y, m, dd = d.split("-"); return f"{int(dd)}.{int(m)}.{y}"
def medal_badge(m):
    return f'<span class="medal {m.lower()}">{M[m]} {m}</span>'
def conf(c):
    return ('<sup title="Club inferred from season roster (this tournament\'s entry '
            'list showed nationality only)">&deg;</sup>') if c == "roster-inferred" else ""

CSS = """
:root{--red:#d10a10;--yellow:#fbb900;--dark:#1d1d1b;--gray:#eee;--line:#ddd;--muted:#666;
--gold-t:#c08a00;--bronze-t:#8a4b1d;}
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Oxygen,Ubuntu,Cantarell,"Fira Sans","Droid Sans","Helvetica Neue",sans-serif;color:#000;background:#fff;line-height:1.5}
a{color:var(--red);text-decoration:none}a:hover{text-decoration:underline}
.banner{background:var(--yellow);color:#000;text-align:center;font-size:14px;padding:9px 16px}
.banner a{color:#000;text-decoration:underline;font-weight:600}
.topnav{display:flex;align-items:center;justify-content:space-between;max-width:1280px;margin:0 auto;padding:14px 24px}
.topnav .brand{font-size:22px;font-weight:700;color:#000}
.topnav .site{color:#000;font-weight:600;font-size:15px}
.hero{max-width:1280px;margin:0 auto;padding:0 16px}
.hero-card{background:var(--red);border-radius:16px;color:#fff;text-align:center;padding:44px 24px 40px;
background-image:repeating-linear-gradient(45deg,rgba(0,0,0,.05) 0 14px,transparent 14px 28px),repeating-linear-gradient(-45deg,rgba(0,0,0,.05) 0 14px,transparent 14px 28px)}
.hero-card .logo{width:118px;height:118px;margin:0 auto 18px}
.hero-card h1{margin:0 0 8px;font-size:clamp(28px,4.5vw,44px);font-weight:700}
.hero-card p{margin:3px auto;max-width:660px;font-size:15px;opacity:.92}
.hero-card a{color:#fff;text-decoration:underline}
.wrap{max-width:1120px;margin:0 auto;padding:0 24px}
.tabs{position:sticky;top:0;z-index:10;background:#fff;display:flex;gap:8px;flex-wrap:wrap;padding:14px 0;border-bottom:1px solid var(--line);margin-bottom:24px}
.tabs button{border:1px solid #000;background:#fff;color:#000;padding:8px 20px;border-radius:0;font-size:15px;font-weight:600;cursor:pointer;font-family:inherit}
.tabs button:hover{background:#f5f5f5}
.tabs button.active{background:var(--red);color:#fff;border-color:var(--red)}
.subtabs{display:flex;gap:8px;flex-wrap:wrap;margin:4px 0 18px;justify-content:center}
.subtabs button{border:1px solid #000;background:#fff;color:#000;padding:5px 14px;border-radius:0;font-size:13px;font-weight:600;cursor:pointer;font-family:inherit}
.subtabs button.active{background:var(--dark);color:#fff;border-color:var(--dark)}
section.tab{display:none}section.tab.active{display:block}
section.tab,.notewrap{background:var(--gray);border-radius:16px;padding:30px 30px 26px;margin:0 0 26px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(118px,1fr));margin:4px 0 26px;background:#fff;border-radius:8px;padding:16px 0}
.stat{padding:8px 10px;text-align:center;border-left:1px solid var(--line)}
.stat:first-child{border-left:none}
.stat .n{font-size:32px;font-weight:700}.stat .l{font-size:11px;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);margin-top:2px}
h2{margin:4px 0 14px;font-size:clamp(24px,3vw,34px);font-weight:700;text-align:center}
.intro{text-align:center;max-width:720px;margin:0 auto 20px;color:#333;font-size:15px}
table{width:100%;border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden}
th,td{padding:9px 12px;text-align:left;border-bottom:1px solid var(--gray);font-size:14px;vertical-align:top}
th{background:#fff;font-size:12px;text-transform:uppercase;letter-spacing:.5px;color:#000;border-bottom:2px solid var(--dark)}
tr:last-child td{border-bottom:none}td.c,th.c{text-align:center}td.r,th.r{text-align:right}
.medal{display:inline-block;font-size:12px;font-weight:600;padding:1px 8px;border-radius:4px;white-space:nowrap}
.medal.gold{background:#fdeeb8;color:#7a5c00}.medal.silver{background:#e8e8e8;color:#555}.medal.bronze{background:#f3e0d0;color:#7a4318}
.gp{color:var(--gold-t)}.sp{color:#777}.bp{color:var(--bronze-t)}
.partner{color:var(--muted);font-size:13px}
.note{background:#fff;border-radius:8px;border-left:4px solid var(--yellow);padding:16px 18px;font-size:13px;color:#333}
details summary{cursor:pointer;font-weight:600;color:var(--red);margin:4px 0}.name{font-weight:600}
.pgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:12px;align-items:start}
.pcard{background:#fff;border-radius:8px;padding:12px 14px}
.toprow{display:flex;justify-content:space-between;align-items:baseline;gap:12px}
.nm{flex:1;min-width:0;font-weight:700;font-size:15px;color:#000;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
a.nm{color:var(--red)}
.rkn{color:var(--muted);font-weight:600;font-size:12px;margin-right:6px}
.pts{font-weight:700;white-space:nowrap}
.pts small{color:var(--muted);font-weight:600;font-size:10px;text-transform:uppercase;letter-spacing:.4px}
.pts.muted{font-weight:600}
.pbar{height:4px;background:var(--gray);margin:9px 0 0;overflow:hidden}
.pbar i{display:block;height:100%;background:var(--red)}
.botrow{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-top:10px}
.botrow details{flex:1;min-width:0;margin:0}
.botrow summary{display:inline-block;cursor:pointer;list-style:none;border:1px solid #000;background:#fff;color:#000;font-size:12px;font-weight:600;padding:4px 12px;margin:0;border-radius:0}
.botrow summary::-webkit-details-marker{display:none}
.botrow summary::after{content:" ▾"}
.botrow details[open] summary{background:var(--dark);color:#fff;border-color:var(--dark)}
.botrow details[open] summary::after{content:" ▴"}
.ddbtns{display:flex;gap:8px;flex-wrap:wrap}
.botrow .ddbtn{cursor:pointer;border:1px solid #000;background:#fff;color:#000;font-size:12px;font-weight:600;padding:4px 12px;margin:0;border-radius:0;font-family:inherit}
.botrow .ddbtn::after{content:" ▾"}
.botrow .ddbtn.open{background:var(--dark);color:#fff;border-color:var(--dark)}
.botrow .ddbtn.open::after{content:" ▴"}
.ddpanes>.evlist[hidden]{display:none}
.evlist{font-size:13px;margin-top:10px;border-top:1px solid var(--gray);padding-top:8px}
.evlist .ev{margin:0 0 7px}
.evlist .ev:last-child{margin-bottom:0}
.evl{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.evlist .partner{display:block;padding-left:1.5em}
.evlist .sub{display:block;color:var(--muted);font-size:12px}
.medbtn{cursor:pointer;font-family:inherit;border:1px solid #000;background:#fff;color:#000;font-size:12px;font-weight:600;padding:2px 10px}
.medbtn::after{content:" ▾"}
.medbtn.open{background:var(--dark);color:#fff;border-color:var(--dark)}
.medbtn.open::after{content:" ▴"}
tr.medrow{display:none}
tr.medrow.open{display:table-row}
tr.medrow td{padding:2px 12px 12px}
tr.medrow .evlist{border-top:none;margin:0;padding:0;text-align:left;columns:360px;column-gap:36px}
tr.medrow .ev{break-inside:avoid}
tr:has(+ tr.medrow.open) td{border-bottom:none}
summary:focus-visible,.medbtn:focus-visible,.ddbtn:focus-visible{outline:2px solid var(--red);outline-offset:2px}
.medals{white-space:nowrap;font-size:13px;font-weight:600;color:#333}
sup{color:var(--red);font-weight:700}.muted{color:var(--muted)}.pill{font-size:11px;background:var(--gray);color:#333;border-radius:4px;padding:1px 7px}
.footer{background:var(--dark);color:#fff;margin-top:76px;text-align:center;padding:0 24px 26px}
.footer .logo{width:96px;height:96px;margin:-48px auto 20px}
.footer .links{display:flex;gap:26px;justify-content:center;flex-wrap:wrap;font-weight:600;margin:0 0 8px}
.footer a{color:#fff}
.footer .rule{border-top:1px solid rgba(255,255,255,.15);max-width:1072px;margin:22px auto}
.footer .copy{font-size:13px;color:rgba(255,255,255,.75)}
.logo{display:block}.logo svg{width:100%;height:100%;display:block}
@media (max-width:760px){
.banner{font-size:13px;padding:8px 12px}
.topnav{padding:12px 16px}
.hero{padding:0 10px}
.hero-card{padding:28px 16px 26px}.hero-card .logo{width:90px;height:90px}
.hero-card p{overflow-wrap:anywhere}
.wrap{padding:0 12px}
.tabs{display:grid;grid-template-columns:repeat(2,1fr);gap:6px;padding:10px 0}
.tabs button{white-space:nowrap;padding:8px 4px;font-size:13px;text-align:center}
.subtabs{justify-content:flex-start}
section.tab,.notewrap{padding:16px 12px}
.stats{grid-template-columns:repeat(3,1fr);padding:10px 0}
.stat{border-left:none;padding:6px 8px}.stat .n{font-size:24px}
/* The tournaments table collapses into cards: name + date, location, stat trio. */
table,tbody{display:block}
thead{display:none}
table{background:transparent;border-radius:0;overflow:visible}
tr{display:flex;flex-wrap:wrap;align-items:baseline;background:#fff;border-radius:8px;padding:12px 14px 10px;margin:0 0 10px}
tr:last-child{margin-bottom:0}
td,tr:last-child td{display:block;border:none;padding:0}
td.tn{order:1;flex:1;min-width:0;font-weight:600;padding-right:12px}
td.dt{order:2;color:var(--muted);font-size:13px;white-space:nowrap}
td.muted{order:3;flex:0 0 100%;font-size:13px;margin:1px 0 10px}
td.c{order:4;flex:1;text-align:left;font-weight:600;font-size:15px}
td.c::before{content:attr(data-l);display:block;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);margin-bottom:2px}
td.c:empty::after{content:"0";color:var(--muted)}
tr.medrow{display:none}
tr.medrow.open{display:block;margin:-10px 0 10px;border-radius:0 0 8px 8px;padding:0 14px 12px}
tr:has(+ tr.medrow.open){border-bottom-left-radius:0;border-bottom-right-radius:0}
tr.medrow td{display:block;padding:0}
tr.medrow .evlist{columns:auto;font-size:13px}
}
"""

JS = """
function tab(id,btn){document.querySelectorAll('section.tab').forEach(s=>s.classList.remove('active'));
 document.getElementById(id).classList.add('active');
 document.querySelectorAll('.tabs button').forEach(b=>b.classList.remove('active'));btn.classList.add('active');window.scrollTo(0,0);}
function subtab(cls,id,btn){document.querySelectorAll('.'+cls).forEach(s=>s.style.display='none');
 document.getElementById(id).style.display='block';
 btn.parentNode.querySelectorAll('button').forEach(b=>b.classList.remove('active'));btn.classList.add('active');}
function medrow(btn){var tr=btn.closest('tr').nextElementSibling;
 var open=tr.classList.toggle('open');btn.classList.toggle('open',open);btn.setAttribute('aria-expanded',open);}
function dd(btn,i){var card=btn.closest('.pcard');var panes=card.querySelectorAll('.ddpanes>.evlist');
 var open=panes[i].hidden;
 card.querySelectorAll('.ddbtn').forEach(function(b){var on=open&&b===btn;b.classList.toggle('open',on);b.setAttribute('aria-expanded',on);});
 panes.forEach(function(p,j){p.hidden=!(open&&j===i);});}
"""

def logo_div():
    """Inline the official club logo SVG (downloaded from tervasulka.fi)."""
    path = os.path.join(T.DATA, "logo-tervasulka.svg")
    try:
        svg = open(path, encoding="utf-8").read()
        svg = svg[svg.index("<svg"):]
        return f'<div class="logo" role="img" aria-label="Tervasulka logo">{svg}</div>'
    except OSError:
        return '<div class="logo" style="font-size:80px">\U0001F3F8</div>'

def run():
    players = json.load(open(os.path.join(T.DATA, "players.json"), encoding="utf-8"))
    tours   = json.load(open(os.path.join(T.DATA, "tournaments.json"), encoding="utf-8"))
    medals  = json.load(open(os.path.join(T.DATA, "tervasulka_medals.json"), encoding="utf-8"))

    tg = sum(p["gold"] for p in players); ts = sum(p["silver"] for p in players); tb = sum(p["bronze"] for p in players)
    medalists = [p for p in players if p["total_medals"] > 0]
    n_played = sum(1 for p in players if p["tournaments_played"] > 0)
    n_inferred = sum(1 for t in medals for m in t["medals"] if m["confidence"] == "roster-inferred")

    o = []
    o.append('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">')
    o.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    o.append("<title>Tervasulka — 2025-26 Season Report</title>")
    o.append("<style>" + CSS + "</style></head><body>")
    logo = logo_div()
    o.append('<div class="banner">Kilpailukausi 2025–26 — tulokset! / Season 2025–26 tournament results '
             '· <a href="https://www.tervasulka.fi/">tervasulka.fi</a></div>')
    o.append('<nav class="topnav"><a class="brand" href="https://www.tervasulka.fi/">Tervasulka</a>'
             '<a class="site" href="https://www.tervasulka.fi/">tervasulka.fi</a></nav>')
    o.append(f'<div class="hero"><div class="hero-card">{logo}')
    o.append('<h1>2025–26 Season Report</h1>')
    o.append(f"<p>Source: <a href='https://badmintonfinland.tournamentsoftware.com'>badmintonfinland.tournamentsoftware.com</a> · Generated {GEN}</p>")
    o.append("</div></div>")
    o.append('<div class="wrap">')

    # tab nav
    o.append('<div class="tabs">')
    tabs = [("ov", "Overview"), ("pl", "Rankings"),
            ("dv", "Divisions"), ("to", "Tournaments")]
    for i, (tid, lbl) in enumerate(tabs):
        o.append(f'<button class="{"active" if i==0 else ""}" onclick="tab(\'{tid}\',this)">{lbl}</button>')
    o.append("</div>")

    # ---------------- shared card template ----------------
    def pcard(name_html, right_html, btn_label, detail_html, medals_html, bar_frac=None,
              btn2_label=None, detail2_html=None):
        bar = f'<div class="pbar"><i style="width:{bar_frac:.0%}"></i></div>' if bar_frac is not None else ""
        if btn2_label is not None or detail2_html:
            # two-dropdown variant: buttons share one panel area below the row and are
            # mutually exclusive — dd() opens one pane and closes the other.
            btns, panes = [], []
            for label, html in ((btn_label, detail_html), (btn2_label, detail2_html)):
                if not label:
                    continue
                btns.append(f'<button class="ddbtn" aria-expanded="false" '
                            f'onclick="dd(this,{len(panes)})">{label}</button>')
                panes.append(f'<div class="evlist" hidden>{html}</div>')
            return (f'<div class="pcard"><div class="toprow">{name_html}{right_html}</div>{bar}'
                    f'<div class="botrow"><span class="ddbtns">{"".join(btns)}</span>'
                    f'<span class="medals">{medals_html}</span></div>'
                    f'<div class="ddpanes">{"".join(panes)}</div></div>')
        det = (f'<details><summary>{btn_label}</summary><div class="evlist">{detail_html}</div></details>'
               if detail_html else f'<span class="muted" style="font-size:12px">{btn_label}</span>')
        return (f'<div class="pcard"><div class="toprow">{name_html}{right_html}</div>{bar}'
                f'<div class="botrow">{det}<span class="medals">{medals_html}</span></div></div>')

    def medal_tally(g, s, b):
        return " ".join(f"{M[m]}{n}" for m, n in (("Gold", g), ("Silver", s), ("Bronze", b)) if n)

    # ---------------- Overview ----------------
    o.append('<section id="ov" class="tab active">')
    o.append('<div class="stats">')
    for n, l, c in [(len(players), "Players", ""), (len(medalists), "Medalists", ""),
                    (tg+ts+tb, "Total medals", ""), (tg, "Gold", "gp"), (ts, "Silver", "sp"),
                    (tb, "Bronze", "bp"), (len(medals), "Tournaments won", "")]:
        o.append(f'<div class="stat"><div class="n {c}">{n}</div><div class="l">{l}</div></div>')
    o.append("</div>")
    o.append("<h2>Medalists — by medal count</h2>")
    o.append('<div class="pgrid">')
    for i, p in enumerate(medalists, 1):
        lines = []
        for m in p["medals"]:
            pt = f'<span class="partner">w/ {esc(", ".join(m["partners"]))}</span>' if m["partners"] else ""
            lines.append(f'<div class="ev"><span class="evl" title="{esc(m["tournament"])}">'
                         f'{M[m["medal"]]} <b>{esc(m["event"])}</b>{conf(m["confidence"])} @ {esc(m["tournament"])}</span>{pt}</div>')
        n = p["total_medals"]
        nm = f'<span class="nm" title="{esc(p["name"])}"><span class="rkn">#{i}</span>{esc(p["name"])}</span>'
        right = f'<span class="pts">{n} <small>medal{"s" if n != 1 else ""}</small></span>'
        o.append(pcard(nm, right, f'{n} medal{"s" if n != 1 else ""}', "".join(lines),
                       medal_tally(p["gold"], p["silver"], p["bronze"])))
    o.append("</div></section>")

    # ---------------- Players (roster merged with rankings, card grid) ----------------
    o.append('<section id="pl" class="tab">')
    ranked = sorted([p for p in players if p["ranking_points"]], key=lambda p: -p["ranking_points"])
    maxpts = ranked[0]["ranking_points"] if ranked else 1
    o.append(f"<h2>Players — season ranking ({n_played})</h2>")
    o.append('<p class="intro">Everyone who entered a tournament this season (roster from entry lists), sorted by '
             'ranking points earned from <b>this season’s</b> events only. '
             'Click a name for the official ranking page; the events button expands the results.</p>')
    o.append('<div class="pgrid">')
    merged = sorted(players, key=lambda p: (-(p["ranking_points"] or 0), -p["tournaments_played"], p["name"]))
    for i, p in enumerate(merged, 1):
        pts = p["ranking_points"]
        nm_txt = esc(p["name"])
        rkn = f'<span class="rkn">#{i}</span>' if pts else ""
        nm = (f'<a class="nm" href="{esc(p["ranking_url"])}" target="_blank" title="{nm_txt}">{rkn}{nm_txt}</a>'
              if p["ranking_url"] else f'<span class="nm" title="{nm_txt}">{rkn}{nm_txt}</span>')
        right = (f'<span class="pts">{fp(pts)} <small>pts</small></span>' if pts
                 else '<span class="pts muted">&mdash; <small>pts</small></span>')
        rts = p["ranking_tournaments"] or []
        lines = []
        for t in sorted(rts, key=lambda x: -x["points"]):
            evs = ", ".join(f'{esc(e["event"])} {esc(e["placing"])} ({fp(e["points"])})' for e in t["events"])
            link = f'<a href="{esc(t["url"])}" target="_blank">{esc(t["tournament"])}</a>' if t["url"] else esc(t["tournament"])
            dt = fd(t["date"]) if t["date"] else f'wk {esc(t["week"])}'
            lines.append(f'<div class="ev"><span class="evl" title="{esc(t["tournament"])}">'
                         f'<b>{fp(t["points"])}</b> &mdash; {link}</span><span class="sub">{dt} &middot; {evs}</span></div>')
        pointed = {t["tournament"] for t in rts}
        other = [t for t in p["tournaments"] if t[1] not in pointed]
        if other:
            lines.append('<div class="ev"><span class="sub">No season points: '
                         + "; ".join(f"{esc(t[1])} ({fd(t[0])})" for t in other) + "</span></div>")
        n_ev = p["tournaments_played"]
        o.append(pcard(nm, right, f'{n_ev} event{"s" if n_ev != 1 else ""}', "".join(lines),
                       medal_tally(p["gold"], p["silver"], p["bronze"]), (pts or 0) / maxpts))
    o.append("</div></section>")

    # ---------------- Tournaments ----------------
    # Medal rows carry the name as printed by that tournament; fold them onto the
    # canonical display name (shared with the Divisions tab).
    tok2disp = {T.tokens(p["name"]): p["name"] for p in players}
    med_by_gid = {m["tournament_id"].lower(): m["medals"] for m in medals}
    MEDAL_ORDER = {"Gold": 0, "Silver": 1, "Bronze": 2}
    o.append('<section id="to" class="tab">')
    o.append(f"<h2>Tournaments analysed ({len(tours)})</h2>")
    o.append('<p class="intro">Every season event scanned. ° = entry list showed nationality only (club inferred from roster). '
             'Click to open the tournament on tournamentsoftware; click a medal count for the medals.</p>')
    o.append('<table><thead><tr><th>Date</th><th>Tournament</th><th>Location</th><th class="c">Entrants</th>'
             '<th class="c">TeSu Entrants</th><th class="c">TeSu Medals</th></tr></thead><tbody>')
    for t in tours:
        star = "&deg;" if t["entry_list_shows"] == "country_only" else ""
        terva = len(t["tervasulka_entrants"])
        hl = ' style="background:#fff7df"' if t["tervasulka_medals"] else ""
        mm = med_by_gid.get(t["tournament_id"].lower(), [])
        medcell, medrow = "", ""
        if mm:
            lines = []
            for h in sorted(mm, key=lambda h: (MEDAL_ORDER[h["medal"]], h["event"])):
                pls = esc(", ".join(tok2disp.get(T.tokens(p), p) for p in h["tervasulka_players"]))
                partners = [x for x in h["all_players_in_entry"] if x not in h["tervasulka_players"]]
                pt = f'<span class="partner">w/ {esc(", ".join(partners))}</span>' if partners else ""
                lines.append(f'<div class="ev"><span class="evl">'
                             f'{M[h["medal"]]} <b>{esc(h["event"])}</b>{conf(h["confidence"])} {pls}</span>{pt}</div>')
            medcell = f'<button class="medbtn" aria-expanded="false" onclick="medrow(this)">{len(mm)}</button>'
            medrow = f'<tr class="medrow"{hl}><td colspan="6"><div class="evlist">{"".join(lines)}</div></td></tr>'
        o.append(f'<tr{hl}><td class="dt">{fd(t["date"])}</td><td class="tn"><a href="{esc(t["url"])}" target="_blank">{esc(t["name"])}</a>{star}</td>'
                 f'<td class="muted">{esc(t["location"])}</td><td class="c" data-l="Entrants">{t["players"]}</td>'
                 f'<td class="c" data-l="TeSu Entrants">{terva or ""}</td><td class="c" data-l="TeSu Medals">{medcell}</td></tr>')
        if medrow:
            o.append(medrow)
    o.append("</tbody></table></section>")

    # ---------------- Divisions (per-player medal tally, like Overview) ----------------
    # division -> player -> {g,s,b, results[]}  (tok2disp shared with Tournaments tab)
    div_players = defaultdict(lambda: defaultdict(lambda: dict(g=0, s=0, b=0, results=[])))
    midx = {"Gold": "g", "Silver": "s", "Bronze": "b"}
    for t in medals:
        for m in t["medals"]:
            d = m["division"]
            for pl in m["tervasulka_players"]:
                pl = tok2disp.get(T.tokens(pl), pl)
                rec = div_players[d][pl]
                rec[midx[m["medal"]]] += 1
                partners = [x for x in m["all_players_in_entry"] if x not in m["tervasulka_players"]]
                rec["results"].append((t["date"], t["tournament"], m["event"], m["medal"],
                                       partners, m["confidence"]))
    # division -> player -> season points / event rows in that division's events; every
    # player with points in a division is listed there too, medals or not.
    pts_by_div = defaultdict(lambda: defaultdict(float))
    ev_by_div = defaultdict(lambda: defaultdict(list))
    for p in players:
        for t in (p["ranking_tournaments"] or []):
            for e in t["events"]:
                d = T.division(e["event"])
                pts_by_div[d][p["name"]] += e["points"]
                ev_by_div[d][p["name"]].append((t["date"], t["tournament"], t["url"], t["week"], e))
    for d, plmap in pts_by_div.items():
        for pl, pts in plmap.items():
            if pts > 0:
                div_players[d][pl]  # defaultdict: creates an empty medal record
    present = [d for d in DIV_ORDER if div_players.get(d)]
    o.append('<section id="dv" class="tab">')
    o.append("<h2>Players by division</h2>")
    o.append('<p class="intro">Each division lists every Tervasulka player with season points or a medal '
             'in that division’s events, ranked by points earned there. The medals button expands the '
             'podium results, the events button the point-earning results.</p>')
    o.append('<div class="subtabs">')
    for i, d in enumerate(present):
        n = len(div_players[d])
        o.append(f'<button class="{"active" if i==0 else ""}" onclick="subtab(\'divsec\',\'div_{i}\',this)">{esc(d)} ({n})</button>')
    o.append("</div>")
    for i, d in enumerate(present):
        disp = "block" if i == 0 else "none"
        o.append(f'<div class="divsec" id="div_{i}" style="display:{disp}">')
        def div_pts(pl):
            """Season points earned in this division's events (same classifier as the medal buckets)."""
            return pts_by_div[d].get(pl, 0.0)
        ranked_pl = sorted(div_players[d].items(),
                           key=lambda kv: (-div_pts(kv[0]),
                                           -(kv[1]["g"]*100 + kv[1]["s"]*10 + kv[1]["b"]), kv[0]))
        o.append('<div class="pgrid">')
        for rank, (pl, rec) in enumerate(ranked_pl, 1):
            tot = rec["g"] + rec["s"] + rec["b"]
            lines = []
            for date, tn, ev, md, partners, cf in sorted(rec["results"],
                                                         key=lambda r: (r[0], {"Gold":0,"Silver":1,"Bronze":2}[r[3]])):
                pt = f'<span class="partner">w/ {esc(", ".join(partners))}</span>' if partners else ""
                lines.append(f'<div class="ev"><span class="evl" title="{esc(tn)}">'
                             f'{M[md]} <b>{esc(ev)}</b>{conf(cf)} @ {esc(tn)}</span>{pt}</div>')
            nm = f'<span class="nm" title="{esc(pl)}"><span class="rkn">#{rank}</span>{esc(pl)}</span>'
            dpts = div_pts(pl)
            right = (f'<span class="pts">{fp(dpts)} <small>pts</small></span>' if dpts
                     else '<span class="pts muted">&mdash; <small>pts</small></span>')
            ev_rows = ev_by_div[d].get(pl, [])
            ev_lines = []
            for date, tn, url, week, e in sorted(ev_rows, key=lambda r: -r[4]["points"]):
                link = f'<a href="{esc(url)}" target="_blank">{esc(tn)}</a>' if url else esc(tn)
                dt = fd(date) if date else f'wk {esc(week)}'
                ev_lines.append(f'<div class="ev"><span class="evl" title="{esc(tn)}">'
                                f'<b>{fp(e["points"])}</b> &mdash; {esc(e["event"])} {esc(e["placing"])}</span>'
                                f'<span class="sub">{dt} &middot; {link}</span></div>')
            mbtn = f'{tot} medal{"s" if tot != 1 else ""}' if tot else None
            ebtn = f'{len(ev_rows)} event{"s" if len(ev_rows) != 1 else ""}' if ev_rows else None
            o.append(pcard(nm, right, mbtn, "".join(lines),
                           medal_tally(rec["g"], rec["s"], rec["b"]),
                           btn2_label=ebtn, detail2_html="".join(ev_lines)))
        o.append("</div></div>")
    o.append("</section>")

    # ---------------- notes ----------------
    o.append('<div class="notewrap"><h2>Method &amp; notes</h2><div class="note">')
    o.append(f'<b>Coverage.</b> All season events on tournamentsoftware were scanned; the report keeps the '
             f'{len(tours)} tournaments on the <a href="{T.BASE}/ranking/tournaments.aspx?id={T.RANKING_PUBLICATION}" target="_blank">official ranking list</a> '
             f'(local pool, school and club-internal events award no ranking points and are excluded, medals included). '
             f'Tervasulka medalled in {len(medals)} of them.<br><br>')
    o.append('<b>Roster.</b> Built from tournament <b>entry lists</b> (club = Tervasulka / “TeSu”), so it includes everyone who competed, not just medalists. '
             'Players whose registration ended on an event’s exclude or reserve list (never in a draw) are not counted as participants; '
             'no-shows in a draw are. '
             f'{n_inferred} medal rows come from tournaments whose entry list showed nationality only (marked °); those clubs were matched against the season roster.<br><br>')
    o.append('<b>Ranking points.</b> Taken from each player’s official ranking page, counting only results from '
             '<b>this season’s</b> tournaments (ISO weeks 2025-W33 … 2026-W26); the official total uses a longer '
             'rolling window. All divisions are included — open, junior (U-age) and senior/veteran (35+…). '
             'Identical rows that re-rank the same result across class lists are de-duplicated, and every total is '
             'cross-checked against the per-tournament points pages of the ranking publication (which also recover '
             'players whose own ranking page is missing results).<br><br>')
    o.append('<b>Podium.</b> Gold/Silver/Bronze = 1st/2nd/3rd (incl. tied 3rd/4th); round-robin 4th+ excluded. All age/class categories included.')
    o.append("</div></div>")
    o.append("</div>")  # .wrap
    o.append(f'<footer class="footer">{logo}')
    o.append('<div class="links"><a href="https://www.tervasulka.fi/">tervasulka.fi</a>'
             '<a href="https://www.tervasulka.fi/kilpailut">Kilpailut</a>'
             '<a href="https://badmintonfinland.tournamentsoftware.com">tournamentsoftware.com</a></div>')
    o.append('<div class="rule"></div>')
    o.append(f'<div class="copy">© 2026 Tervasulka ry · 2025–26 season · {len(players)} players · {tg+ts+tb} medals · {len(ranked)} ranked</div>')
    o.append("</footer>")
    o.append("<script>" + JS + "</script></body></html>")

    out = os.path.join(T.REPO, "index.html")
    open(out, "w", encoding="utf-8").write("\n".join(o))
    print(f"step5: HTML -> {out}  ({len(players)} players, {len(medalists)} medalists, "
          f"{len(ranked)} ranked, {len(tours)} tournaments)")

if __name__ == "__main__":
    run()
