"""Official candidate lists from state election offices.

Each reader returns rows of (chamber, district, candidate name, party label) for the
November 2026 general election, already limited to qualified, on-ballot candidates.
Chamber names match build.CHAMBERS. Where a reader returns rows for a chamber, they
replace that chamber's Wikipedia data.
"""
import io
import logging
import re
import urllib.request

from bs4 import BeautifulSoup
from pypdf import PdfReader

UA = "empty-ballot-dashboard/1.0 (civic data project)"
logging.getLogger("pypdf").setLevel(logging.ERROR)  # font-encoding chatter on every PDF page
SENATE, HOUSE = "Senate", "House of Representatives"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read()
        if body.startswith(b"%PDF"):  # layout mode keeps each table row on one line
            return "\n".join(p.extract_text(extraction_mode="layout") for p in PdfReader(io.BytesIO(body)).pages)
        return body.decode(r.headers.get_content_charset() or "utf-8", "replace")


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
            if m and txt(tds[2]) in ("Qualified", "Unopposed") and m.group(3) != "WRI":  # Unopposed = elected outright
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


def nevada(text):
    """Legislative Counsel Bureau roster PDF: District | Name | Party, one blank-line group per district.
    The district number sits on any one line of its group (the middle one for three candidates)."""
    rows, chamber, group, district = [], None, [], ""

    def flush():
        nonlocal district
        district = next((d for d, _, _ in group if d), district)  # no number: a district split across pages
        rows.extend((chamber, f"District {district}", name, p) for _, name, p in group)
        group.clear()

    for line in text.splitlines():
        head = re.search(r"NEVADA STATE (SENATE|ASSEMBLY) CANDIDATES", line)
        m = re.match(r"^\s*(\d+)?\s{2,}(\S.*?)\s{3,}([A-Z][A-Za-z ]+?)\s*$", line)
        if head or not line.strip():
            if group:
                flush()
            if head:
                chamber = SENATE if head.group(1) == "SENATE" else "Assembly"
        elif chamber and m and not re.search(r"\bNAME\b.*\bPARTY\b", line):  # not the column header
            group.append(m.groups(""))
    if group:
        flush()
    return rows


def wyoming(text):
    """Secretary of State roster PDF: an 'STATE SENATOR 01' heading per office, then two lines per candidate,
    Party | Name | Address | Date filed, and below it City | Date withdrawn."""
    rows, chamber, district = [], None, ""
    for line in text.splitlines():
        if line[:1].strip() and not re.match(r"\w+day, ", line):  # an office heading, not the page footer's date
            m = re.match(r"STATE (SENATOR|REPRESENTATIVE) (\d+)\s*$", line)
            chamber = (SENATE if m.group(1) == "SENATOR" else HOUSE) if m else None
            district = m.group(2).lstrip("0") if m else ""
            continue
        m = re.match(r"^\s{5,20}(\S.*?)\s{3,}(\S.*?)\s{3,}.*?\d\d/\d\d/\d{4}", line)
        if chamber and m:
            rows.append((chamber, f"District {district}", m.group(2), m.group(1)))
        elif chamber and rows and re.search(r"\d\d/\d\d/\d{4}", line):
            rows.pop()  # a date on the city line is the date withdrawn
    return rows


def new_mexico(html):
    """The candidate grid; columns found by header name."""
    trs = BeautifulSoup(html, "html.parser").find_all("tr")
    own = lambda tr: tr.find_all(["th", "td"], recursive=False)  # outer layout rows hold the whole grid
    i = next(i for i, tr in enumerate(trs) if {"Status", "Ballot Order"} <= {txt(c) for c in own(tr)})
    head = [txt(c) for c in own(trs[i])]
    col = {h: head.index(h) for h in ("District", "Name", "Party", "Ballot Order", "Status")}
    rows = []
    for tr in trs[i + 1:]:
        c = [txt(td) for td in own(tr)]
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
    "NV": (nevada, ["https://www.leg.state.nv.us/Division/Research/Documents/CandidatesList_2026General.pdf"]),
    "WY": (wyoming, ["https://sos.wyo.gov/Elections/Docs/2026/2026_WY_General_Election_Candidates.pdf"]),
    "NM": (new_mexico, ["https://candidateportal.servis.sos.state.nm.us/CandidateList.aspx"]),
}


def fetch_state(code):
    """Rows for one state, or [] if it has no reader. Network errors propagate to the caller."""
    if code not in SOURCES:
        return []
    reader, urls = SOURCES[code]
    return reader("\n".join(get(u) for u in urls))
