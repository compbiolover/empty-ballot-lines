"""State election office readers, against markup copied from the live 2026 pages (trimmed)."""
import io
import os
import sys
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))
import states  # noqa: E402
from build import rows_to_races  # noqa: E402

S, H = states.SENATE, states.HOUSE
XLSX = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


class StatesTest(unittest.TestCase):
    def test_colorado(self):
        html = """<table><tr><th>Candidate name</th><th>Office</th><th>District</th><th>Party</th><th>Write in?</th></tr>
        <tr><td>Mark Baisley</td><td>US Senate</td><td>State</td><td>Republican Party</td><td>N</td></tr>
        <tr><td>Jamie Jeffery</td><td>State Senate</td><td>1</td><td>Democratic Party</td><td>N</td></tr>
        <tr><td>Byron Pelton</td><td>State Senate</td><td>1</td><td>Republican Party</td><td>N</td></tr>
        <tr><td>Some Writein</td><td>State Senate</td><td>1</td><td>Unaffiliated</td><td>Y</td></tr>
        <tr><td><s>Gone Person</s></td><td>State House of Representatives</td><td>4</td><td>Republican Party</td><td>N</td></tr>
        <tr><td>Kept Person</td><td>State House of Representatives</td><td>4</td><td>Democratic Party</td><td>N</td></tr></table>"""
        self.assertEqual(states.colorado(html), [
            (S, "District 1", "Jamie Jeffery", "Democratic Party"), (S, "District 1", "Byron Pelton", "Republican Party"),
            (H, "District 4", "Kept Person", "Democratic Party")])

    def test_delaware(self):
        html = """<table><tr><th>Office</th><th>County</th><th>Party</th><th>Candidate</th><th>Status</th><th>Filed</th></tr>
        <tr><td>State Representative District 1</td><td>New Castle</td><td>Democratic</td>
        <td><span class="main-span">Nnamdi O. Chukwuocha<i></i></span> <span class="sub-span">Mailing Address: <br>PO Box 1</span></td>
        <td>Qualified</td><td>5/27/2026</td></tr>
        <tr><td>State Representative District 20</td><td>Sussex</td><td>Republican</td>
        <td><span class="main-span">Withdrawn Guy</span></td><td>Withdrawn</td><td>1/1/2026</td></tr>
        <tr><td>Kent County Sheriff</td><td>Kent</td><td>Democratic</td><td><span class="main-span">X</span></td><td>Qualified</td><td></td></tr></table>"""
        self.assertEqual(states.delaware(html), [(H, "District 1", "Nnamdi O. Chukwuocha", "Democratic")])

    def test_florida(self):
        row = ('<tr><td><b>{d}</b></td><td><a> </a><a>{last}</a><a>, </a><a>{first}</a><a>&nbsp; </a> ({p}) {inc}</td>'
               '<td>{s} </td><td>Unopposed</td><td>&nbsp;</td></tr>')
        hdr = "<tr><td><b> District </b></td><th>Candidate</th><th>Status</th><th>Primary</th><th>General</th></tr>"
        html = (f'<table><tr><td><table><tr><td>Candidate Listing for 2026 General Election</td></tr></table></td></tr></table>'
                f'<font><b>State Senator</b></font><table>{hdr}'
                + row.format(d="2", last="Donahoo", first="Lauren", p="DEM", inc="", s="Qualified")
                + row.format(d="&nbsp;", last="Trumbull", first="Jay", p="REP", inc="*Incumbent", s="Qualified")
                + "</table><font><b>State Representative</b></font><table>" + hdr
                + row.format(d="13", last="Gaillard", first="Brice", p="WRI", inc="", s="Qualified")
                + row.format(d="&nbsp;", last="Rutledge", first="Shemiah", p="DEM", inc="", s="Withdrew")
                + row.format(d="&nbsp;", last="Smith", first="Ann", p="NPA", inc="", s="Qualified")
                + row.format(d="14", last="Elected", first="Already", p="REP", inc="", s="Unopposed") + "</table>")
        self.assertEqual(states.florida(html), [
            (S, "District 2", "Lauren Donahoo", "DEM"), (S, "District 2", "Jay Trumbull", "REP"),
            (H, "District 13", "Ann Smith", "NPA"), (H, "District 14", "Already Elected", "REP")])

    def test_minnesota(self):
        text = ("MN;;;0188;State Representative District 1A;1A;0301;John Burkel;;;R;0;174;0;0.00;0\n"
                "MN;;;0188;State Representative District 1A;1A;0402;Leanna Sandahl;;;DFL;0;174;0;0.00;0\n"
                "MN;;;0188;State Representative District 1A;1A;9901;WRITE-IN;;;WI;0;174;0;0.00;0\n"
                "MN;;;0121;State Senator District 1;1;0301;Mark Johnson;;;R;33;315;100;16.67;600\r\n")
        rows = states.minnesota(text)
        self.assertEqual(rows, [(H, "District 1A", "John Burkel", "R"), (H, "District 1A", "Leanna Sandahl", "DFL"),
                                (S, "District 1", "Mark Johnson", "R")])
        races = rows_to_races([r[1:] for r in rows if r[0] == H])
        self.assertEqual((races[0]["category"], races[0]["majors"]), ("two_party", "DR"))  # bare R and DFL codes

    def test_nevada(self):
        text = """                            NEVADA STATE SENATE CANDIDATES

  DISTRICT          NAME                                                            PARTY

    2               Edgar Flores*                                                  Democrat


                    Matthew R. Buehler                                             Republican
    13              Richard “Skip” Daly*                                           Democrat
                    Charlene Young                                                 Independent American

*Incumbent
                                                     2026 General Election: Nevada Legislative Candidates | July 2026 | p. 2
                              NEVADA STATE ASSEMBLY CANDIDATES
  DISTRICT             NAME                                                                     PARTY
    6                  Katherine “Katie” Duncan                                                 No Political Party
                       Jovan Alexander Jackson*                                                 Democrat
"""
        self.assertEqual(states.nevada(text), [
            (S, "District 2", "Edgar Flores*", "Democrat"), (S, "District 13", "Matthew R. Buehler", "Republican"),
            (S, "District 13", "Richard “Skip” Daly*", "Democrat"), (S, "District 13", "Charlene Young", "Independent American"),
            ("Assembly", "District 6", "Katherine “Katie” Duncan", "No Political Party"),
            ("Assembly", "District 6", "Jovan Alexander Jackson*", "Democrat")])

    def test_wyoming(self):
        text = """ Office Sought
             Party Affiliation            Candidate Name                            Mailing Address                     Date Filed         Campaign Telephone
                                                                                    City, State & ZIP           Date Withdrawn             Email
GOVERNOR

           Republican                    Eric Barlow                               1625 A Buffalo Cut Across Rd       05/16/2026         307-209-4846
                                                                                   Gillette, WY 82718                                    eric@barlowforwyo.com
STATE SENATOR 05

           Republican                    Lauren Schoenfeld                        2325 Torben Ct                      05/14/2026        307-922-6136
                                                                                  Cheyenne, WY 82009                                    laurenschoenfeld307@gmail.com
Wednesday, September 09, 2026 - 11:20AM                                                                                                                                          Page 2 of 19
           Democratic                    Ted Hanlon                               808 West Dale Blvd                  05/15/2026        307-275-9556
                                                                                  Cheyenne, WY 82009                                    ted@hanlon4wyoming.com
STATE REPRESENTATIVE 62

           Republican                    Gone Person                              1 Main St                           05/15/2026        307-555-0100
                                                                                  Casper, WY 82601            06/01/2026                gone@example.com
           Democratic                    Kept Person                              2 Main St                           05/15/2026        307-555-0101
                                                                                  Casper, WY 82601                                      kept@example.com
JUDGE OF THE CHANCERY COURT                                                                                                                                         Ben Burningham
           Retain                        Ben Burningham                           3 Main St                           05/15/2026
"""
        self.assertEqual(states.wyoming(text), [
            (S, "District 5", "Lauren Schoenfeld", "Republican"), (S, "District 5", "Ted Hanlon", "Democratic"),
            (H, "District 62", "Kept Person", "Democratic")])

    def test_missouri(self):
        text = """         REPUBLICAN CANDIDATES
         For U.S. Representative
         District 4, Mark Alford
         For State Senator
         District 2, Nick Schroer
                                                                        8
     District 30, Melanie Stinnett
     For State Representative
     District 48, T im Taylor
     For Circuit Judge
     Circuit 11 Division 1, Brittney R. Smith
 DEMOCRATIC CANDIDATES
 For State Representative
 District 48, Jane Doe
"""
        self.assertEqual(states.missouri(text), [
            (S, "District 2", "Nick Schroer", "Republican"), (S, "District 30", "Melanie Stinnett", "Republican"),
            (H, "District 48", "T im Taylor", "Republican"), (H, "District 48", "Jane Doe", "Democratic")])

    def test_kansas(self):
        def tr(*c):
            return "<tr>" + "".join(f"<td>{x}</td>" for x in c) + "</tr>"
        html = ("<table><tr><th>Candidate</th><th>Office</th><th>District</th><th>Position</th><th>Division</th><th>Party</th></tr>"
                + tr("Roger Marshall", "United States Senate", "0", "0", "0", "Republican")
                + tr("Dale Helwig", "Kansas House of Representatives", "1", "0", "0", "Republican")
                + tr("Pat Proctor", "Kansas Senate", "5", "0", "0", "Republican") + "</table>")
        self.assertEqual(states.kansas(html), [(H, "District 1", "Dale Helwig", "Republican")])

    def test_north_dakota(self):
        def tr(contest, name, party):
            return (f'<tr class="rgRow"><td data-title="Contest:">{contest}</td><td>4</td>'
                    f'<td data-title="Name:">{name}</td><td data-title="Party:">{party}</td></tr>')
        html = ("<table>" + tr("State Senator<br />District 07", "A Person", "Republican")
                + tr("State Representative<br />District 05", "B Person", "Democratic-NPL")
                + tr("State Representative<br />District 05", "C Person", "Republican")
                + tr("State Representative<br />District 05", "D Person", "Republican")
                + tr("State Representative Unexpired 2-Year Term<br />District 26", "E Person", "Republican")
                + tr("County Sheriff<br />Burleigh", "F Person", "Republican") + "</table>")
        rows = states.north_dakota(html)
        self.assertEqual(rows, [(S, "District 7", "A Person", "Republican", 1),
                                (H, "District 5", "B Person", "Democratic-NPL", 2), (H, "District 5", "C Person", "Republican", 2),
                                (H, "District 5", "D Person", "Republican", 2), (H, "District 26", "E Person", "Republican", 1)])
        races = rows_to_races([r[1:] for r in rows if r[0] == H])
        self.assertEqual([(r["seats"], r["category"]) for r in races], [(2, "two_party"), (1, "unopposed")])

    def test_vermont(self):
        sheet = ('<sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="C1" t="s"><v>2</v></c>'
                 '<c r="D1" t="s"><v>3</v></c><c r="E1" t="s"><v>4</v></c><c r="O1" t="s"><v>5</v></c></row>')
        for i, (contest, dist, name, party, n) in enumerate([
                ("STATE SENATOR", "CHI CT 1", "ANN ONE", "PROG/DEM", "THREE"),
                ("STATE SENATOR", "CHI CT 1", "BOB TWO", "REP/DEM", "THREE"),
                ("STATE REPRESENTATIVE", "ADD 1", "CY THREE", "INDEPENDENT", "TWO"),
                ("SHERIFF", "ADDISON", "DEE FOUR", "REPUBLICAN", "ONE")], start=2):
            sheet += (f'<row r="{i}">' + "".join(f'<c r="{col}{i}" t="inlineStr"><is><t>{v}</t></is></c>'
                      for col, v in zip("ABCDEO", (contest, dist, name, "TOWN", party, n))) + "</row>")
        heads = ["Contest", "District Name", "Name On Ballot", "Town Of Residence", "Party", "Vote for Count"]
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("xl/worksheets/sheet1.xml", f'<worksheet xmlns="{XLSX}">{sheet}</sheetData></worksheet>')
            z.writestr("xl/sharedStrings.xml", f'<sst xmlns="{XLSX}">' + "".join(f"<si><t>{h}</t></si>" for h in heads) + "</sst>")
        rows = states.vermont(states.xlsx_text(buf.getvalue()))
        self.assertEqual(rows, [(S, "CHI CT 1", "ANN ONE", "PROG/DEM", 3), (S, "CHI CT 1", "BOB TWO", "REP/DEM", 3),
                                (H, "ADD 1", "CY THREE", "INDEPENDENT", 2)])
        senate = rows_to_races([r[1:] for r in rows if r[0] == S])[0]
        self.assertEqual([c["party"] for c in senate["candidates"]], ["D", "R"])  # first major party in a fused label
        self.assertEqual((senate["seats"], senate["category"]), (3, "unopposed"))

    def test_new_mexico(self):
        head = ["Contest", "Contest", "District", "Filing County", "Name", "Party", "Ballot Order", "Status"]
        def tr(*c):
            return "<tr>" + "".join(f"<td>{x}</td>" for x in c) + "</tr>"
        html = ("<table><tr><td><table><tr><td>Export: Excel PDF CSV</td></tr></table></td></tr>"
                + "<tr>" + "".join(f"<th>{h}</th>" for h in head) + "</tr>"
                + tr("State RepresentativeDISTRICT 1", "State Representative", "DISTRICT 1", "San Juan", "ROD MONTOYA", "REP", "1", "Qualified")
                + tr("State RepresentativeDISTRICT 4", "State Representative", "DISTRICT 4", "San Juan", "JOE H", "REP", "1", "Withdrawn")
                + tr("State RepresentativeDISTRICT 4", "State Representative", "DISTRICT 4", "San Juan", "WRITE IN", "DTS", "99", "Qualified")
                + tr("United States SenatorSTATE", "United States Senator", "STATE", "", "X", "DEM", "1", "Qualified") + "</table>")
        self.assertEqual(states.new_mexico(html), [(H, "District 1", "ROD MONTOYA", "REP")])


if __name__ == "__main__":
    unittest.main()
