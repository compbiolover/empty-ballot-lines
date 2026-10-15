"""State election office readers, against markup copied from the live 2026 pages (trimmed)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))
import states  # noqa: E402
from build import rows_to_races  # noqa: E402

S, H = states.SENATE, states.HOUSE


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
                + row.format(d="&nbsp;", last="Smith", first="Ann", p="NPA", inc="", s="Qualified") + "</table>")
        self.assertEqual(states.florida(html), [
            (S, "District 2", "Lauren Donahoo", "DEM"), (S, "District 2", "Jay Trumbull", "REP"),
            (H, "District 13", "Ann Smith", "NPA")])

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

    def test_massachusetts(self):
        html = """<main><h2>Councillor</h2><h3>First District</h3><p>Not Counted, 1 St., Town, Democratic</p>
        <h2>Senator in General Court</h2><h3>First Bristol &amp; Plymouth District</h3>
        <p>Michael J. Rodrigues, 428 Sanford Rd., Westport, Democratic</p>
        <p>John Smith, Jr., 1 Main St., Fall River, Republican</p>
        <h2>Representative in General Court</h2><h3>Second Barnstable District</h3>
        <p>Joe B. Glynn, 822 Route 28, Yarmouth, Gulf War Veteran</p>
        <h2>District Attorney</h2><h3>Cape District</h3><p>Not Counted, 2 St., Town, Republican</p></main>"""
        self.assertEqual(states.massachusetts(html), [
            (S, "First Bristol & Plymouth District", "Michael J. Rodrigues", "Democratic"),
            (S, "First Bristol & Plymouth District", "John Smith, Jr.", "Republican"),
            (H, "Second Barnstable District", "Joe B. Glynn", "Gulf War Veteran")])

    def test_new_mexico(self):
        head = ["Contest", "Contest", "District", "Filing County", "Name", "Party", "Ballot Order", "Status"]
        def tr(*c):
            return "<tr>" + "".join(f"<td>{x}</td>" for x in c) + "</tr>"
        html = ("<table>" + "<tr>" + "".join(f"<th>{h}</th>" for h in head) + "</tr>"
                + tr("State RepresentativeDISTRICT 1", "State Representative", "DISTRICT 1", "San Juan", "ROD MONTOYA", "REP", "1", "Qualified")
                + tr("State RepresentativeDISTRICT 4", "State Representative", "DISTRICT 4", "San Juan", "JOE H", "REP", "1", "Withdrawn")
                + tr("State RepresentativeDISTRICT 4", "State Representative", "DISTRICT 4", "San Juan", "WRITE IN", "DTS", "99", "Qualified")
                + tr("United States SenatorSTATE", "United States Senator", "STATE", "", "X", "DEM", "1", "Qualified") + "</table>")
        self.assertEqual(states.new_mexico(html), [(H, "District 1", "ROD MONTOYA", "REP")])


if __name__ == "__main__":
    unittest.main()
