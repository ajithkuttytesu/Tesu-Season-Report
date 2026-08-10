"""Shared helpers for the Tervasulka tournament scraper.

Handles the tournamentsoftware cookie-wall, cached HTTP fetches, and the
small parsing utilities (name tokenisation, country detection, event-division
and medal classification) used across the pipeline steps.
"""
import os, re, html, time, datetime, urllib.request, urllib.parse, http.cookiejar

BASE = "https://badmintonfinland.tournamentsoftware.com"
UA   = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0 Safari/537.36"

REPO  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(REPO, ".cache")
DATA  = os.path.join(REPO, "data")
os.makedirs(CACHE, exist_ok=True)
os.makedirs(DATA, exist_ok=True)

# Tervasulka identifiers on the platform
TERVA_RANKING_OGID = "7C7F710E-BF72-4C15-8F3E-CABA47B736A3"
RANKING_PUBLICATION = "53055"   # weekly ranking publication (latest as of 9.8.2026)
CLUB_NAMES = ("tervasulka", "tesu")

# ---------------------------------------------------------------- HTTP session
_cj = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_cj))
_opener.addheaders = [("User-Agent", UA)]
_session_ready = False

def _ensure_session():
    """Accept the cookie-wall once so later requests aren't redirected to it."""
    global _session_ready
    if _session_ready:
        return
    try:
        _opener.open(BASE + "/", timeout=40).read()
    except Exception:
        pass
    body = urllib.parse.urlencode(
        {"ReturnUrl": "/", "SettingsOpen": "False", "CookiePurposes": "1"}).encode()
    try:
        _opener.open(BASE + "/cookiewall/Save", data=body, timeout=40).read()
    except Exception:
        pass
    _session_ready = True

def fetch(path, cache_name=None, xhr=False, post=None, retries=3):
    """GET (or POST) a path, returning text. Uses an on-disk cache when given."""
    if cache_name:
        p = os.path.join(CACHE, cache_name)
        if os.path.exists(p) and os.path.getsize(p) > 0:
            return open(p, encoding="utf-8", errors="ignore").read()
    _ensure_session()
    url = path if path.startswith("http") else BASE + path
    data = urllib.parse.urlencode(post).encode() if post is not None else None
    last = ""
    for _ in range(retries):
        try:
            req = urllib.request.Request(url, data=data)
            if xhr:
                req.add_header("X-Requested-With", "XMLHttpRequest")
            text = _opener.open(req, timeout=40).read().decode("utf-8", "ignore")
            if cache_name:
                open(os.path.join(CACHE, cache_name), "w", encoding="utf-8").write(text)
            return text
        except Exception as e:
            last = str(e); time.sleep(1.5)
    return last if False else ""

# ----------------------------------------------------------------- text helpers
def unesc(s):
    return html.unescape(s).strip()

# Manual identity fixes: variants the token matcher cannot merge on its own
# (transliteration differences, initials vs. full surname).  Maps a variant's
# token-key to the canonical token-key.
NAME_ALIASES = {
    frozenset({"diana", "volkhonskaja"}): frozenset({"diana", "volkhonskaia"}),
    frozenset({"shreeharsha", "b", "v"}): frozenset({"shreeharsha", "banavasi", "venkatesh"}),
}
# Preferred display name when the automatic pick among variants is wrong.
DISPLAY_OVERRIDES = {
    frozenset({"shreeharsha", "banavasi", "venkatesh"}): "Shreeharsha Banavasi Venkatesh",
}

def tokens(name):
    """Order-independent name key: 'Last, First' and 'First Last' map equal."""
    n = re.sub(r"\s*\[[0-9/]+\]", "", name)        # drop seed markers
    n = re.sub(r"\s+", " ", n.replace(",", " ")).strip().lower()
    key = frozenset(n.split())
    return NAME_ALIASES.get(key, key)

def clean_name(name):
    return re.sub(r"\s*\[[0-9/]+\]", "", name).strip()

def norm_tname(n):
    """Normalised tournament-name key: drop parentheticals and years, lowercase."""
    n = re.sub(r"\(.*?\)", "", n)
    n = re.sub(r"\b20\d\d\b", "", n)
    return re.sub(r"\s+", " ", n).strip().lower()

def isoweek(date):
    """'YYYY-MM-DD' -> ISO week key 'YYYY-W' as used by the ranking pages."""
    y, w, _ = datetime.date.fromisoformat(date).isocalendar()
    return f"{y}-{w}"

def ranking_tournaments():
    """(normalised name, ISO week) of every tournament in the ranking publication.

    Tournaments absent from this list award no ranking points; the pipeline
    excludes them (and their medals) from the published dataset."""
    return {(norm_tname(t["name"]), t["week"]) for t in ranking_tournament_index()}

def ranking_tournament_index():
    """Every tournament in the ranking publication with its ranking tournament id.

    Returns a list of dicts (tid, name, week).  The tid addresses the
    per-tournament points page /ranking/tournament.aspx?id=<pub>&tournament=<tid>,
    which itemises the points every player earned at that tournament."""
    doc = fetch(f"/ranking/tournaments.aspx?id={RANKING_PUBLICATION}",
                cache_name=f"rktournaments_{RANKING_PUBLICATION}.html")
    flat = re.sub(r"\s+", " ", doc)
    out, seen = [], set()
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", flat):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr)
        cells = [unesc(re.sub(r"<[^>]+>", "", c)) for c in tds]
        if len(cells) >= 3 and re.match(r"20\d\d-\d{1,2}$", cells[2]):
            m = re.search(r"tournament\.aspx\?id=\d+&(?:amp;)?tournament=(\d+)", tr)
            if m and m.group(1) not in seen:
                seen.add(m.group(1))
                out.append(dict(tid=m.group(1), name=cells[1], week=cells[2]))
    return out

def ranking_tournament_points(tid):
    """Parse a tournament's ranking-points page: who earned what at this event.

    Returns a list of dicts (category, member_id, name, placing, points), one
    row per player per category, in page order."""
    doc = fetch(f"/ranking/tournament.aspx?id={RANKING_PUBLICATION}&tournament={tid}",
                cache_name=f"rktour_{tid}.html")
    flat = re.sub(r"\s+", " ", doc)
    rows, category = [], None
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", flat):
        cm = re.search(r'category\.aspx\?id=\d+&(?:amp;)?category=\d+"?>([^<]+)</a>', tr)
        if cm and "<th" in tr:
            category = unesc(cm.group(1))
            continue
        pm = re.search(r'player\.aspx\?id=\d+&(?:amp;)?player=(\d+)"?>([^<]+)</a>', tr)
        cells = [unesc(re.sub(r"<[^>]+>", "", c)) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr)]
        if pm and len(cells) >= 4:
            pts = cells[3].replace("\xa0", "").replace(" ", "").replace(",", ".")
            try:
                pts = float(pts)
            except ValueError:
                continue
            rows.append(dict(category=category, member_id=pm.group(1),
                             name=unesc(pm.group(2)), placing=cells[2], points=pts))
    return rows

_COUNTRIES = {
 'finland','sweden','india','norway','denmark','estonia','germany','china','iceland','latvia',
 'lithuania','poland','france','spain','england','scotland','ireland','netherlands','ukraine',
 'russia','japan','vietnam','thailand','indonesia','malaysia','usa','canada','italy','belgium',
 'austria','switzerland','czechia','slovakia','hungary','portugal','bulgaria','romania','greece',
 'turkey','israel','egypt','nigeria','south africa','australia','sri lanka','pakistan','bangladesh',
 'nepal','iran','brazil','mexico','peru','faroe islands'}
def is_country(v):
    v = v.strip()
    return v.lower() in _COUNTRIES or (len(v) == 3 and v.isupper())

# --------------------------------------------------------- classification logic
def is_medal(place):
    return place in ("1", "2", "3", "3/4", "3-4")
def medal_name(place):
    return {"1": "Gold", "2": "Silver", "3": "Bronze", "3/4": "Bronze", "3-4": "Bronze"}[place]

def division(event):
    """Map an event label to a division bucket for the report tabs."""
    e = " " + event.upper().replace("-", " ") + " "
    if re.search(r"\bU\s?\d+\b", e) or re.search(r"\b(BS|GS|BD|GD|BX|GX|PS|PD|TS|TD|POJAT|TYTÖT)\b", e):
        return "Junior"
    if re.search(r"\b(35|40|45|50|55|60|65|70|75|80)\b", e):
        return "Senior"
    if re.search(r"\b(V|VALIO|ELIT|ELITE)\b", e):
        return "Valio/Elite"
    if re.search(r"\bA\b", e) or "AVOIN" in e or "KILPA" in e or "ADVANCED" in e:
        return "A"
    if re.search(r"\bB\b", e):
        return "B"
    if re.search(r"\bC\b", e):
        return "C"
    if re.search(r"\bD\b", e):
        return "D"
    return "Other"

def tournament_url(gid):
    return f"{BASE}/tournament/{gid.lower()}"
def winners_url(gid):
    return f"{BASE}/sport/winners.aspx?id={gid.lower()}"
def ranking_player_url(member_id):
    return f"{BASE}/ranking/player.aspx?id={RANKING_PUBLICATION}&player={member_id}"
