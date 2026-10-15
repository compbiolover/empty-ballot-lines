"""Official candidate lists from state election offices.

Each reader returns rows of (chamber, district, candidate name, party label) for the
November 2026 general election, already limited to qualified, on-ballot candidates.
Chamber names match build.CHAMBERS. Where a reader returns rows for a chamber, they
replace that chamber's Wikipedia data.
"""
import re
import urllib.request

from bs4 import BeautifulSoup

UA = "empty-ballot-dashboard/1.0 (civic data project)"
SENATE, HOUSE = "Senate", "House of Representatives"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode(r.headers.get_content_charset() or "utf-8", "replace")


def txt(el):
    return re.sub(r"\s+", " ", el.get_text(" ")).strip() if el else ""


def colorado(html):
    """One plain table: Candidate name | Office | District | Party | Write in?"""
    rows = []
    for tr in BeautifulSoup(html, "html.parser").find_all("tr"):
        c = [txt(td) for td in tr.find_all("td")]
        chamber = {"State Senate": SENATE, "State House of Representatives": HOUSE}.get(c[1] if len(c) > 4 else "")
        if chamber and not c[4].upper().startswith("Y") and not tr.find(["s", "strike", "del"]):  # struck = withdrawn
            rows.append((chamber, f"District {c[2]}", c[0], c[3]))
    return rows


def delaware(html):
    """Office | County | Party | Candidate (name plus hidden contact block) | Status | Filed"""
    rows = []
    for tr in BeautifulSoup(html, "html.parser").find_all("tr"):
        tds = tr.find_all("td")
        m = re.match(r"State (Senator|Representative) (District \d+)", txt(tds[0])) if len(tds) > 4 else None
        if m and txt(tds[4]) == "Qualified":
            name = tds[3].find(class_="main-span") or tds[3]
            rows.append((SENATE if m.group(1) == "Senator" else HOUSE, m.group(2), txt(name), txt(tds[2])))
    return rows


def florida(html):
    """Two tables (State Senator, State Representative): District | 'Last, First (PTY)' | Status | ..."""
    rows = []
    for table in BeautifulSoup(html, "html.parser").find_all("table"):
        head = table.find_previous("font")
        chamber = SENATE if "Senator" in txt(head) else HOUSE if "Representative" in txt(head) else None
        if not chamber or table.find("table") or "Candidate" not in txt(table.find("tr")):
            continue  # layout tables wrap the two lists; skip them
        district = ""
        for tr in table.find_all("tr")[1:]:
            tds = tr.find_all("td")
            if len(tds) < 3:
                continue
            district = txt(tds[0]) or district  # blank on a district's later candidates
            m = re.match(r"(.*?),\s*(.*?)\s*\((\w+)\)", txt(tds[1]))
            if m and txt(tds[2]) == "Qualified" and m.group(3) != "WRI":
                rows.append((chamber, f"District {district}", f"{m.group(2).strip()} {m.group(1).strip()}", m.group(3)))
    return rows


def minnesota(text):
    """Semicolon results-file layout; field 5 office, 6 district, 8 name, 11 party."""
    rows = []
    for line in text.splitlines():
        f = line.strip().split(";")
        if len(f) > 10 and f[10] != "WI" and f[7].upper() != "WRITE-IN":
            chamber = SENATE if f[4].startswith("State Senator") else HOUSE if f[4].startswith("State Representative") else None
            if chamber:
                rows.append((chamber, f"District {f[5]}", f[7], f[10]))
    return rows


def massachusetts(html):
    """h2 office, h3 district, then one <p> per candidate: 'Name, street, town, Party'."""
    rows, chamber, district = [], None, ""
    main = BeautifulSoup(html, "html.parser")
    for el in main.find_all(["h2", "h3", "p"]):
        if el.name == "h2":
            chamber = {"Senator in General Court": SENATE, "Representative in General Court": HOUSE}.get(txt(el))
        elif el.name == "h3":
            district = txt(el)
        elif chamber and district:
            parts = [p.strip() for p in txt(el).rsplit(",", 3)]  # names can hold commas; the last 3 fields can't
            if len(parts) == 4 and parts[0]:
                rows.append((chamber, district, parts[0], parts[3]))
    return rows


def new_mexico(html):
    """Largest table; columns found by header name."""
    tables = BeautifulSoup(html, "html.parser").find_all("table")
    table = max(tables, key=lambda t: len(t.find_all("tr")))
    trs = table.find_all("tr")
    head = [txt(c) for c in trs[0].find_all(["th", "td"])]
    col = {h: head.index(h) for h in ("District", "Name", "Party", "Ballot Order", "Status")}
    rows = []
    for tr in trs[1:]:
        c = [txt(td) for td in tr.find_all(["td", "th"])]
        if len(c) > col["Status"] and c[1] == "State Representative" and c[col["Status"]] == "Qualified" \
                and c[col["Ballot Order"]] != "99":  # 99 = write-in
            rows.append((HOUSE, c[col["District"]].title(), c[col["Name"]], c[col["Party"]]))
    return rows


# state code -> (reader, [urls]); a reader takes the fetched text of each url, concatenated
SOURCES = {
    "CO": (colorado, ["https://www.sos.state.co.us/pubs/elections/vote/generalCandidates.html"]),
    "DE": (delaware, ["https://elections.delaware.gov/candidates/candidatelist/genl_fcddt_2026.html"]),
    "FL": (florida, ["https://dos.elections.myflorida.com/candidates/CanList.asp"
                     "?elecid=20261103-GEN&OfficeGroup=LEG&StatusCode=ALL&OrderBy=OFF"]),
    "MN": (minnesota, ["https://electionresultsfiles.sos.mn.gov/20261103/LegislativeByDistrict.txt",
                       "https://electionresultsfiles.sos.mn.gov/20261103/stsenate.txt"]),
    "MA": (massachusetts, ["https://www.sec.state.ma.us/divisions/elections/research-and-statistics/"
                           "2026-state-election-candidates.htm"]),
    "NM": (new_mexico, ["https://candidateportal.servis.sos.state.nm.us/CandidateList.aspx"]),
}


def fetch_state(code):
    """Rows for one state, or [] if it has no reader. Network errors propagate to the caller."""
    if code not in SOURCES:
        return []
    reader, urls = SOURCES[code]
    return reader("\n".join(get(u) for u in urls))
