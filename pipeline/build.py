"""Build site/data/seats.{json,csv}: every 2026 state legislative race and who is on the ballot.

Source: the per-chamber "2026 <State> <Chamber> election" pages on Wikipedia, read through the
MediaWiki parse API. Each page carries a district table (incumbent, status, candidates).

Run: python pipeline/build.py
"""
import colorsys
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from bs4 import BeautifulSoup, NavigableString, Tag

import states

YEAR = 2026
API = "https://en.wikipedia.org/w/api.php"
UA = f"empty-ballot-dashboard/1.0 (https://github.com/{os.environ.get('GITHUB_REPOSITORY', '')})"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "site", "data")

# The 88 chambers with regular elections on Nov 3, 2026 (LA, MS, NJ, VA vote in odd years;
# the KS, NM and SC senates are not up). Chamber names follow Wikipedia's page titles.
CHAMBERS = [
    ("AL", "Alabama", "House of Representatives"), ("AL", "Alabama", "Senate"),
    ("AK", "Alaska", "House of Representatives"), ("AK", "Alaska", "Senate"),
    ("AZ", "Arizona", "House of Representatives"), ("AZ", "Arizona", "Senate"),
    ("AR", "Arkansas", "House of Representatives"), ("AR", "Arkansas", "Senate"),
    ("CA", "California", "State Assembly"), ("CA", "California", "State Senate"),
    ("CO", "Colorado", "House of Representatives"), ("CO", "Colorado", "Senate"),
    ("CT", "Connecticut", "House of Representatives"), ("CT", "Connecticut", "State Senate"),
    ("DE", "Delaware", "House of Representatives"), ("DE", "Delaware", "Senate"),
    ("FL", "Florida", "House of Representatives"), ("FL", "Florida", "Senate"),
    ("GA", "Georgia", "House of Representatives"), ("GA", "Georgia", "State Senate"),
    ("HI", "Hawaii", "House of Representatives"), ("HI", "Hawaii", "Senate"),
    ("ID", "Idaho", "House of Representatives"), ("ID", "Idaho", "Senate"),
    ("IL", "Illinois", "House of Representatives"), ("IL", "Illinois", "Senate"),
    ("IN", "Indiana", "House of Representatives"), ("IN", "Indiana", "Senate"),
    ("IA", "Iowa", "House of Representatives"), ("IA", "Iowa", "Senate"),
    ("KS", "Kansas", "House of Representatives"),
    ("KY", "Kentucky", "House of Representatives"), ("KY", "Kentucky", "Senate"),
    ("ME", "Maine", "House of Representatives"), ("ME", "Maine", "Senate"),
    ("MD", "Maryland", "House of Delegates"), ("MD", "Maryland", "Senate"),
    ("MA", "Massachusetts", "House of Representatives"), ("MA", "Massachusetts", "Senate"),
    ("MI", "Michigan", "House of Representatives"), ("MI", "Michigan", "Senate"),
    ("MN", "Minnesota", "House of Representatives"), ("MN", "Minnesota", "Senate"),
    ("MO", "Missouri", "House of Representatives"), ("MO", "Missouri", "Senate"),
    ("MT", "Montana", "House of Representatives"), ("MT", "Montana", "Senate"),
    ("NE", "Nebraska", "Legislature"),
    ("NV", "Nevada", "Assembly"), ("NV", "Nevada", "Senate"),
    ("NH", "New Hampshire", "House of Representatives"), ("NH", "New Hampshire", "Senate"),
    ("NM", "New Mexico", "House of Representatives"),
    ("NY", "New York", "State Assembly"), ("NY", "New York", "State Senate"),
    ("NC", "North Carolina", "House of Representatives"), ("NC", "North Carolina", "Senate"),
    ("ND", "North Dakota", "House of Representatives"), ("ND", "North Dakota", "Senate"),
    ("OH", "Ohio", "House of Representatives"), ("OH", "Ohio", "Senate"),
    ("OK", "Oklahoma", "House of Representatives"), ("OK", "Oklahoma", "Senate"),
    ("OR", "Oregon", "House of Representatives"), ("OR", "Oregon", "State Senate"),
    ("PA", "Pennsylvania", "House of Representatives"), ("PA", "Pennsylvania", "State Senate"),
    ("RI", "Rhode Island", "House of Representatives"), ("RI", "Rhode Island", "Senate"),
    ("SC", "South Carolina", "House of Representatives"),
    ("SD", "South Dakota", "House of Representatives"), ("SD", "South Dakota", "Senate"),
    ("TN", "Tennessee", "House of Representatives"), ("TN", "Tennessee", "Senate"),
    ("TX", "Texas", "House of Representatives"), ("TX", "Texas", "Senate"),
    ("UT", "Utah", "House of Representatives"), ("UT", "Utah", "Senate"),
    ("VT", "Vermont", "House of Representatives"), ("VT", "Vermont", "Senate"),
    ("WA", "Washington", "House of Representatives"), ("WA", "Washington", "State Senate"),
    ("WV", "West Virginia", "House of Delegates"), ("WV", "West Virginia", "Senate"),
    ("WI", "Wisconsin", "State Assembly"), ("WI", "Wisconsin", "Senate"),
    ("WY", "Wyoming", "House of Representatives"), ("WY", "Wyoming", "Senate"),
]


# ---------- fetching ----------

def api(**params):
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json", "formatversion": 2})
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except (urllib.error.URLError, TimeoutError):
            if attempt == 3:
                raise
            time.sleep(5 * 2 ** attempt)


def page_html(state, chamber):
    """Return (resolved title, html) for the chamber's election page, or (None, None)."""
    title = f"{YEAR} {state} {chamber} election"
    d = api(action="parse", page=title, prop="text", redirects=1)
    if "error" in d:  # title differs from our guess: take the first search hit for this year and state
        hits = api(action="opensearch", search=title, limit=5)[1]
        hit = next((h for h in hits if h.startswith(f"{YEAR} {state} ")), None)
        if not hit:
            return None, None
        d = api(action="parse", page=hit, prop="text", redirects=1)
        if "error" in d:
            return None, None
    return d["parse"]["title"], d["parse"]["text"]


# ---------- parsing ----------

def clean(s):
    return re.sub(r"\s+", " ", re.sub(r"\[[^\]]*\]", "", s)).replace("▌", "").strip()


def text(cell):
    return clean(cell.get_text(" "))


def lines(cell):
    """One string per entry in a list-like cell (bullets or <br>-separated)."""
    items = cell.find_all("li")
    if items:
        return [t for t in (clean(li.get_text(" ")) for li in items) if t]
    for br in cell.find_all("br"):
        br.replace_with("\n")
    return [t for t in (clean(s) for s in cell.get_text(" ").split("\n")) if t]


def party(s):
    """'R', 'D' or 'O'. Fusion/cross-nominated labels take the first major party named."""
    code = s.strip().strip(".").upper()  # official lists use bare codes
    if code in ("R", "REP", "GOP"):
        return "R"
    if code in ("D", "DEM", "DFL"):
        return "D"
    s = s.lower()
    hits = [(s.find(k), code) for k, code in
            (("republican", "R"), ("democrat", "D"), ("dfl", "D"), ("farmer", "D")) if k in s]
    return min(hits)[1] if hits else "O"


COLOR = re.compile(r"color\s*:\s*(#[0-9a-f]{3}(?:[0-9a-f]{3})?)\b", re.I)
SKIP_ROW = re.compile(r"^(no candidate|none|vacant|n/?a)\b|^[-—–]+$", re.I)
EXCLUDE = re.compile(r"primary|special|runoff|caucus|convention|recall|voided|nominat", re.I)
GENERIC = {"district", "house", "senate", "state", "of", "representatives", "representative", "delegates",
           "assembly", "election", "elections", "general", "results", "result", "the", "s", "legislative", "ld",
           "hd", "sd", "ad", "legislature", "and"}
STATE_WORDS = {w for _, s, _ in CHAMBERS for w in s.lower().split()} | {"louisiana", "mississippi", "jersey", "virginia"}


def color_party(hexcol):
    """Party from a Wikipedia party-colour swatch: blue is Democratic, red is Republican, anything else Other."""
    h = hexcol.lstrip("#")
    h = "".join(c * 2 for c in h) if len(h) == 3 else h
    hue, light, sat = colorsys.rgb_to_hls(*(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)))
    if sat < 0.35 or not 0.1 < light < 0.85:
        return "O"
    hue *= 360
    return "D" if 185 <= hue <= 260 else "R" if hue <= 15 or hue >= 340 else "O"


def person(name, label="", col=None):
    """A candidate dict, or None for write-ins and blank slots. TBD stays, with an unknown party."""
    name = re.sub(r"\s*\((incumbent|inc\.|presumptive)\)", "", name, flags=re.I).strip(" '*")
    if not name or "write-in" in f"{name} {label}".lower() or SKIP_ROW.match(name):
        return None
    if label.upper() in ("", "TBD") and name.upper() == "TBD":
        return {"name": name, "party": "?", "label": "TBD"}  # a TBD under a named party keeps that party
    p = party(label) if label else color_party(col) if col else "?"
    if label and p == "O" and col:  # an unhelpful label such as a nickname: trust the swatch
        p = color_party(col)
    return {"name": name, "party": p, "label": label or {"D": "Democratic", "R": "Republican"}.get(p, "")}


def swatch_items(node):
    """Split a cell fragment at each party-colour swatch (▌) into (text, colour) pairs."""
    out, buf, col = [], [], None
    for el in node.descendants:
        if isinstance(el, Tag):
            m = COLOR.search(el.get("style", ""))
            if m and el.name == "span" and not text(el):
                if clean("".join(buf)):
                    out.append((clean("".join(buf)), col))
                buf, col = [], m.group(1)
        elif type(el) is NavigableString:  # skips <style>, comments
            buf.append(str(el))
    if clean("".join(buf)):
        out.append((clean("".join(buf)), col))
    return out


def candidates(cell):
    items = cell.find_all("li")
    if not items:
        parts = re.split(r"<br\s*/?>", str(cell), flags=re.I)
        items = [BeautifulSoup(p, "html.parser") for p in parts] if len(parts) > 1 else [cell]
    out = []
    for item in items:
        for line, col in swatch_items(item):
            m = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", line)
            if m and m.group(2).lower() in ("incumbent", "inc.", "presumptive"):
                m = None
            c = person(m.group(1), m.group(2), col) if m else person(line, "", col)
            if c:
                out.append(c)
    return out


def district_key(s):
    """Comparable district id: 'Connecticut's 1st House district election, 2026' and 'District 1' both give '1'."""
    s = re.sub(r"\b(19|20)\d\d\b", " ", s.lower())
    s = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", s)
    toks = [t for t in re.findall(r"\d+[a-z]?\b|[a-z]+", s) if t not in GENERIC and t not in STATE_WORDS]
    return " ".join(toks) if any(t[0].isdigit() for t in toks) else None


def parse_boxes(soup):
    """General-election result boxes ({{Election box}}), one per district section."""
    races = {}
    for t in soup.find_all("table"):
        first = t.find(["th", "td"])
        if not t.find("tr", class_="vcard") or (first and re.match(r"district|seat", text(first), re.I)):
            continue  # not a result box, or a whole-chamber district table (handled by parse_table)
        cap = text(t.caption) if t.caption else ""
        heads = [text(h) for h in t.find_all_previous(["h2", "h3", "h4", "h5", "h6"], limit=4)]
        if EXCLUDE.search(cap) or (heads and EXCLUDE.search(heads[0])):
            continue
        key = district_key(cap) or next((k for k in map(district_key, heads) if k), None)
        if not key or key in races:
            continue
        rows = t.find_all("tr")
        sections = [i for i, tr in enumerate(rows) if not tr.find("td") and re.match(r"general election", text(tr), re.I)]
        cands = []
        for tr in rows[sections[0] if sections else 0:]:  # a box can hold the primary and the general
            fn = tr.find(class_="fn") if "vcard" in (tr.get("class") or []) else None
            if not fn:
                continue
            org = tr.find(class_="org")
            swatch = tr.find("td", style=COLOR)
            c = person(text(fn), text(org) if org else "", COLOR.search(swatch["style"]).group(1) if swatch else None)
            if c:
                cands.append(c)
        m = re.search(r"(\d+)\s+to be elected", cap, re.I)
        seats = int(m.group(1)) if m else 1  # shortcut: multi-member boxes without "N to be elected" count as 1 seat
        cat, majors = classify(cands, seats)
        races[key] = {"district": f"District {key.title()}", "seats": seats, "incumbent_party": "", "status": "",
                      "candidates": cands, "category": cat, "majors": majors}
    return list(races.values())


def span(cell, attr):
    m = re.match(r"\d+", cell.get(attr, "1") or "1")
    return max(int(m.group()), 1) if m else 1


def grid(table):
    """Rows of the table with rowspan/colspan expanded; a spanned cell repeats in every slot it covers."""
    rows, pending = [], {}  # column -> (cell, rows still to cover)
    for tr in table.find_all("tr"):
        if tr.find_parent("table") is not table:
            continue
        cells = iter(tr.find_all(["td", "th"], recursive=False))
        row, col, nxt = [], 0, next(cells, None)
        while nxt is not None or col in pending:
            if col in pending:
                cell, left = pending.pop(col)
                if left > 1:
                    pending[col] = (cell, left - 1)
                row.append(cell)
                col += 1
                continue
            rs = span(nxt, "rowspan")
            for _ in range(span(nxt, "colspan")):
                if rs > 1:
                    pending[col] = (nxt, rs - 1)
                row.append(nxt)
                col += 1
            nxt = next(cells, None)
        rows.append(row)
    return rows


def classify(cands, seats):
    majors = {c["party"] for c in cands} & {"D", "R"}
    if not cands or any(c["party"] == "?" for c in cands):
        cat = "unknown"  # nobody listed yet, a slot still TBD, or a party we couldn't read: don't guess
    elif len(cands) <= seats:
        cat = "unopposed"
    elif majors == {"D", "R"}:
        cat = "two_party"
    else:
        cat = "one_party"
    return cat, "".join(sorted(majors)) or "none"


def parse_table(table):
    h = table.find_previous(["h2", "h3", "h4", "h5", "h6"])
    if EXCLUDE.search((text(table.caption) if table.caption else "") + " " + (text(h) if h else "")):
        return []  # primary-results tables list district + candidates too
    g = grid(table)
    n = next((i for i, r in enumerate(g) if any(c.name == "td" for c in r)), 0)
    if not n:
        return []
    width = max(len(r) for r in g[:n])
    labels = [" ".join(dict.fromkeys(text(r[i]) for r in g[:n] if i < len(r))).lower() for i in range(width)]
    if EXCLUDE.search(" ".join(labels)):
        return []  # title row inside the header, e.g. "... Democratic primary"
    if not re.search(r"district|seat|constituency", labels[0]):
        return []  # summary or per-race result tables, not the district list
    cand_cols = [i for i, l in enumerate(labels) if "candidate" in l]
    if not cand_cols:
        return []
    cand = next((i for i in cand_cols if "general" in labels[i]), cand_cols[-1])

    def col(*words):
        return next((i for i, l in enumerate(labels) if i not in (0, cand) and any(w in l for w in words)), None)

    member, inc_party, status, position = col("member", "incumbent"), col("party"), col("status"), col("position")
    cand_party = cand - 1 if "party" in labels[cand - 1] else None  # PA-style: one candidate per row, party beside it
    races = {}
    for row in g[n:]:
        if cand >= len(row) or row[cand].name != "td":
            continue
        get = lambda i: row[i] if i is not None and i < len(row) else None
        cands = candidates(row[cand])
        if cand_party is not None and len(cands) == 1 and cands[0]["party"] == "?":
            swatch = next((COLOR.search(c.get("style", "")) for c in row[:cand_party] if COLOR.search(c.get("style", ""))), None)
            cands = [c for c in [person(cands[0]["name"], text(row[cand_party]), swatch and swatch.group(1))] if c]
        shared = span(row[cand], "rowspan") > 1  # one candidates cell over several member rows: a multi-member race
        key = id(row[cand]) if shared else (id(row[0]), text(get(position)) if get(position) is not None else "")
        if key in races:  # same race again: another member row, or another candidate row (PA-style)
            races[key]["rows"] += shared
            races[key]["candidates"] += [] if shared else cands
            continue
        district = text(row[0])
        if get(position) is not None and text(row[position]):
            district = f"{district} (Position {text(row[position])})"
        races[key] = {
            "district": district,
            "rows": 1,
            "members": len(lines(get(member))) if get(member) is not None else 1,
            "incumbent_party": party(text(get(inc_party))) if get(inc_party) is not None else "",
            "status": text(get(status)) if get(status) is not None else "",
            "candidates": cands,
        }
    out = []
    for r in races.values():
        if not r["district"]:
            continue
        seats = max(r.pop("rows"), r.pop("members"))
        r["seats"] = seats
        r["category"], r["majors"] = classify(r["candidates"], seats)
        out.append(r)
    return out


def parse_infobox(box):
    """One race from a per-district election infobox (pages with a '## District N' section per seat)."""
    rows = {}
    for tr in box.find_all("tr"):
        cells = tr.find_all(["th", "td"], recursive=False)
        if len(cells) > 1:
            rows.setdefault(text(cells[0]).lower(), [text(c) for c in cells[1:] if text(c)])
    head = box.find(["caption", "tr"])
    title = text(head).lower() if head else ""
    parties = rows.get("party", [])
    names = rows.get("nominee") or rows.get("candidate") or []
    if "primary" in title:
        # A primary box stands in for the general only when the page says nobody else filed.
        if "not contested" in text(box).lower() or "not currently contested" in text(box).lower():
            parties, names = parties[:1], names[:1]
        else:
            parties = []  # keep the seat, as "unknown"
    cands = [c for c in (person(names[i] if i < len(names) else "TBD", p) for i, p in enumerate(parties)) if c]
    cat, majors = classify(cands, 1)
    return {"district": "", "seats": 1, "incumbent_party": "", "status": "", "candidates": cands,
            "category": cat, "majors": majors}


def parse_page(html):
    """Races from three layouts Wikipedia uses, merged by district: a district table, per-district
    election boxes, and per-district infoboxes. The first source that names the candidates wins."""
    soup = BeautifulSoup(html, "html.parser")
    table = [r for t in soup.find_all("table") for r in parse_table(t)]
    infobox = []
    for box in soup.select("table.infobox"):
        h = box.find_previous(["h2", "h3"])
        district = text(h) if h else ""
        if re.match(r"district\b", district, re.I) and not EXCLUDE.search(district) and not re.search(r"\d{4}", district):
            infobox.append({**parse_infobox(box), "district": district})
    known = lambda rs: [r for r in rs if r["category"] != "unknown"]
    merged = {}
    boxes = parse_boxes(soup)
    for r in known(table) + known(boxes) + known(infobox) + table + boxes + infobox:
        merged.setdefault(district_key(r["district"]) or r["district"], r)
    return list(merged.values())


def rows_to_races(rows):
    """Races from (district, name, party label) rows of an official list; one seat per district."""
    by = {}
    for district, name, label in rows:
        c = person(name, label)
        by.setdefault(district, [])
        if c:
            by[district].append(c)
    out = []
    for district, cands in by.items():
        cat, majors = classify(cands, 1)  # shortcut: all current official readers are single-member states
        out.append({"district": district, "seats": 1, "incumbent_party": "", "status": "",
                    "candidates": cands, "category": cat, "majors": majors})
    return out


# ---------- main ----------

def main():
    os.makedirs(OUT, exist_ok=True)
    prev_path = os.path.join(OUT, "seats.json")
    prev = {}
    if os.path.exists(prev_path):
        with open(prev_path) as f:
            for r in json.load(f)["races"]:
                prev.setdefault((r["state"], r["chamber"]), []).append(r)

    official = {}  # state code -> rows from its election office, fetched once per state
    races, chambers = [], []
    for code, state, chamber in CHAMBERS:
        info = {"state": code, "state_name": state, "chamber": chamber, "page": None, "stale": False, "error": None,
                "source": "wikipedia"}
        if code not in official:
            try:
                official[code] = (states.fetch_state(code), None)
            except Exception as e:  # a broken state site must not stop the run; fall back to Wikipedia
                official[code] = ([], f"state source: {e}")
        rows, info["error"] = official[code]
        rs = rows_to_races([r[1:] for r in rows if r[0] == chamber])
        if rs:
            info["source"], info["page"] = "state", states.SOURCES[code][1][0]
        else:
            try:
                info["page"], html = page_html(state, chamber)
                rs = parse_page(html) if html else []
            except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as e:
                rs, info["error"] = [], str(e)
        if not rs and info["error"] and prev.get((code, chamber)):  # a fetch failed: keep last good data
            rs, info["stale"] = prev[(code, chamber)], True
        for r in rs:
            r.update(state=code, chamber=chamber, upper="Senate" in chamber)
        info["races"] = len(rs)
        info["seats"] = sum(r["seats"] for r in rs)
        info["unknown_seats"] = sum(r["seats"] for r in rs if r["category"] == "unknown")
        print(f"{code} {chamber:26} races={info['races']:4} seats={info['seats']:4} {info['source']}"
              f"{' STALE' if info['stale'] else ''}{' ERROR ' + info['error'] if info['error'] else ''}")
        races += rs
        chambers.append(info)
        time.sleep(1)  # be polite to the API

    if not races:
        sys.exit("No races parsed; leaving existing data untouched.")

    meta = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "year": YEAR,
            "source": "State election office candidate lists where available, otherwise Wikipedia chamber election "
                      "pages (CC BY-SA 4.0)", "chambers": chambers}
    with open(prev_path, "w") as f:
        json.dump({"meta": meta, "races": races}, f, separators=(",", ":"))
    with open(os.path.join(OUT, "seats.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["state", "chamber", "district", "seats", "category", "major_parties",
                    "incumbent_party", "status", "candidates"])
        for r in races:
            w.writerow([r["state"], r["chamber"], r["district"], r["seats"], r["category"], r["majors"],
                        r["incumbent_party"], r["status"],
                        "; ".join(f"{c['name']} ({c['label']})" for c in r["candidates"])])
    print(f"Wrote {len(races)} races / {sum(r['seats'] for r in races)} seats from {len(chambers)} chambers.")


if __name__ == "__main__":
    main()
