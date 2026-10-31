"""Official candidate lists from state election offices.

Each reader returns rows of (chamber, district, candidate name, party label[, seats]) for the
November 2026 general election, already limited to qualified, on-ballot candidates. Seats
default to 1 when a reader leaves them out.
Chamber names match build.CHAMBERS. Where a reader returns rows for a chamber, they
replace that chamber's Wikipedia data.
"""
import http.cookiejar
import io
import logging
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

from bs4 import BeautifulSoup
from pypdf import PdfReader

UA = "empty-ballot-dashboard/1.0 (civic data project)"
logging.getLogger("pypdf").setLevel(logging.ERROR)  # font-encoding chatter on every PDF page
SENATE, HOUSE = "Senate", "House of Representatives"


def get(url, choices=None, button=None):
    """The page as text; PDFs and spreadsheets are converted. With choices, the page is an ASP.NET search
    form: each <select> whose name contains a key is set to the option with that text, then `button` is pressed."""
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    opener.addheaders = [("User-Agent", UA)]
    data = None
    if choices:  # the form only accepts a postback from the same session that loaded it
        with opener.open(url, timeout=60) as r:
            soup = BeautifulSoup(r.read().decode("utf-8", "replace"), "html.parser")
        form = {i["name"]: i.get("value", "") for i in soup.select("input[type=hidden]") if i.get("name")}
        for sel in soup.find_all("select"):
            want = next((v for k, v in choices.items() if k in sel["name"]), None)
            opts = sel.find_all("option")
            opt = next(o for o in opts if txt(o) == want) if want else sel.find("option", selected=True) or opts[0]
            form[sel["name"]] = opt.get("value", "")
        submit = soup.find("input", attrs={"type": "submit", "value": button})
        form[submit["name"]] = button
        data = urllib.parse.urlencode(form).encode()
    with opener.open(url, data, timeout=60) as r:
        body = r.read()
        if body.startswith(b"%PDF"):  # layout mode keeps each table row on one line
            return "\n".join(p.extract_text(extraction_mode="layout") for p in PdfReader(io.BytesIO(body)).pages)
        if body.startswith(b"PK"):
            return xlsx_text(body)
        return body.decode(r.headers.get_content_charset() or "utf-8", "replace")


def xlsx_text(body):
    """The first sheet of an .xlsx workbook as tab-separated lines."""
    m = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    z = zipfile.ZipFile(io.BytesIO(body))
    shared = [] if "xl/sharedStrings.xml" not in z.namelist() else [
        "".join(t.text or "" for t in si.iter(m + "t")) for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(m + "si")]
    lines = []
    for row in ET.fromstring(z.read("xl/worksheets/sheet1.xml")).iter(m + "row"):
        cells = {}
        for c in row.iter(m + "c"):
            v = c.find(m + "v")
            col = sum((ord(ch) - 64) * 26 ** i for i, ch in enumerate(reversed(re.match(r"[A-Z]+", c.get("r")).group())))
            cells[col] = shared[int(v.text)] if c.get("t") == "s" else "".join(t.text or "" for t in c.iter(m + "t")) \
                if c.get("t") == "inlineStr" else v.text if v is not None else ""
        lines.append("\t".join(cells.get(i, "").replace("\t", " ") for i in range(1, max(cells, default=0) + 1)))
    return "\n".join(lines)


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

def missouri(text):
    """Secretary of State certification PDF: a 'REPUBLICAN CANDIDATES' heading per party, then 'For <office>'
    headings, then 'District N, Name' lines."""
    rows, party, chamber = [], "", None
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        m = re.fullmatch(r"([A-Z ]+) CANDIDATES", line)
        if m:
            party, chamber = m.group(1).title(), None
        elif line.startswith("For "):
            chamber = {"For State Senator": SENATE, "For State Representative": HOUSE}.get(line)
        elif chamber and (m := re.fullmatch(r"District (\d+), (.+)", line)):
            rows.append((chamber, f"District {m.group(1)}", m.group(2), party))
    return rows


def kansas(html):
    """The candidate grid: Candidate | Office | District | Position | Division | Party | ..."""
    rows = []
    for tr in BeautifulSoup(html, "html.parser").find_all("tr"):
        c = [txt(td) for td in tr.find_all("td")]
        if len(c) > 5 and c[1] == "Kansas House of Representatives":  # the senate is not up in 2026
            rows.append((HOUSE, f"District {c[2]}", c[0], c[5]))
    return rows


def north_dakota(html):
    """Search results, one row per candidate, cells labelled by data-title. House districts elect two,
    except a race for one unexpired term ('State Representative Unexpired 2-Year Term District 20')."""
    rows = []
    for tr in BeautifulSoup(html, "html.parser").select("tr.rgRow, tr.rgAltRow"):
        cell = lambda t: txt(tr.find("td", attrs={"data-title": t}))
        m = re.fullmatch(r"State (Senator|Representative)( Unexpired .*?)? District 0*(\d+)", cell("Contest:"))
        if m:
            house = m.group(1) == "Representative"
            rows.append((HOUSE if house else SENATE, f"District {m.group(3)}", cell("Name:"), cell("Party:"),
                         2 if house and not m.group(2) else 1))
    return rows


def vermont(text):
    """Qualified-candidates workbook: Contest | District Name | Name On Ballot | Town | Party | ... | Vote for Count."""
    lines = [line.split("\t") for line in text.splitlines()]
    head = next(c for c in lines if "Vote for Count" in c)
    col = {h: head.index(h) for h in ("Contest", "District Name", "Name On Ballot", "Party", "Vote for Count")}
    seats = {"ONE": 1, "TWO": 2, "THREE": 3}
    rows = []
    for c in lines:
        chamber = {"STATE SENATOR": SENATE, "STATE REPRESENTATIVE": HOUSE}.get(c[col["Contest"]] if len(c) > col["Contest"] else "")
        if chamber:
            rows.append((chamber, c[col["District Name"]], c[col["Name On Ballot"]], c[col["Party"]],
                         seats[c[col["Vote for Count"]]]))
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


# state code -> (reader, [urls]); a reader takes the fetched text of each url, concatenated.
# A (url, choices, button) entry is a search form; see get().
ND_LIST = "https://vip.sos.nd.gov/candidatelist.aspx?eid=348"
SOURCES = {
    "CO": (colorado, ["https://www.sos.state.co.us/pubs/elections/vote/generalCandidates.html"]),
    "DE": (delaware, ["https://elections.delaware.gov/candidates/candidatelist/genl_fcddt_2026.html"]),
    "FL": (florida, ["https://dos.elections.myflorida.com/candidates/CanList.asp"
                     "?elecid=20261103-GEN&OfficeGroup=LEG&StatusCode=ALL&OrderBy=OFF"]),
    "MN": (minnesota, ["https://electionresultsfiles.sos.mn.gov/20261103/LegislativeByDistrict.txt",
                       "https://electionresultsfiles.sos.mn.gov/20261103/stsenate.txt"]),
    "NV": (nevada, ["https://www.leg.state.nv.us/Division/Research/Documents/CandidatesList_2026General.pdf"]),
    "WY": (wyoming, ["https://sos.wyo.gov/Elections/Docs/2026/2026_WY_General_Election_Candidates.pdf"]),
    "KS": (kansas, [("https://sos.ks.gov/elections/elections_upcoming_candidate.aspx",
                     {"ddlElections": "2026 General"}, "Submit")]),
    "MO": (missouri, ["https://www.sos.mo.gov/CMSImages/ElectionCandidates/2026GeneralElectionCertifiedCandidates.pdf"]),
    "ND": (north_dakota, [(ND_LIST, {"ddlContest": "State Senator"}, "Search"),
                          (ND_LIST, {"ddlContest": "State Representative"}, "Search")]),
    "VT": (vermont, ["https://outside.vermont.gov/dept/sos/Elections_Division/election_info_resources/candidates/"
                     "2026_general_election_qualified_candidates.xlsx"]),
    "NM": (new_mexico, ["https://candidateportal.servis.sos.state.nm.us/CandidateList.aspx"]),
}


def fetch_state(code):
    """Rows for one state, or [] if it has no reader. Network errors propagate to the caller."""
    if code not in SOURCES:
        return []
    reader, urls = SOURCES[code]
    return reader("\n".join(get(*u) if isinstance(u, tuple) else get(u) for u in urls))
