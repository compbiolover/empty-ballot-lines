import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))
from build import district_key, parse_page, party  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "chamber.html")


class ParseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(FIXTURE) as f:
            cls.races = {r["district"]: r for r in parse_page(f.read())}

    def test_ignores_summary_table_and_finds_all_races(self):
        self.assertEqual(sorted(self.races), sorted([
            "District 1", "District 6", "District 20", "District 28", "District 40",
            "LD 3", "LD 9 (Position 1)", "LD 9 (Position 2)", "LD 12", "PA 1", "PA 3"]))

    def test_single_member_categories(self):
        r = self.races
        self.assertEqual((r["District 1"]["category"], r["District 1"]["majors"]), ("unopposed", "R"))
        self.assertEqual(r["District 1"]["candidates"][0]["name"], "Jessica Means")  # ref and swatch stripped
        self.assertEqual(r["District 1"]["status"], "Incumbent lost renomination.")
        self.assertEqual(r["District 1"]["incumbent_party"], "R")
        self.assertEqual((r["District 6"]["category"], r["District 6"]["majors"]), ("two_party", "DR"))
        self.assertEqual(r["District 20"]["category"], "two_party")  # "Democrat" spelling
        # write-in is dropped, independent keeps it contested but without major-party competition
        self.assertEqual((r["District 28"]["category"], r["District 28"]["majors"]), ("one_party", "D"))
        self.assertEqual(len(r["District 28"]["candidates"]), 2)
        self.assertEqual(r["District 40"]["category"], "unknown")  # empty cell is not counted as unopposed

    def test_multi_member_and_positions(self):
        r = self.races
        self.assertEqual(r["LD 3"]["seats"], 2)  # candidates cell spans two member rows
        self.assertEqual((r["LD 3"]["category"], r["LD 3"]["majors"]), ("two_party", "DR"))  # fusion label
        self.assertEqual((r["LD 9 (Position 1)"]["seats"], r["LD 9 (Position 1)"]["category"]), (1, "unopposed"))
        self.assertEqual(r["LD 9 (Position 2)"]["category"], "two_party")  # DFL counts as D
        self.assertEqual((r["LD 12"]["seats"], r["LD 12"]["category"]), (2, "unopposed"))  # two names, one row

    def test_section_infobox_fallback(self):
        with open(os.path.join(os.path.dirname(FIXTURE), "sections.html")) as f:
            r = {x["district"]: x for x in parse_page(f.read())}
        self.assertEqual(sorted(r), ["District 1", "District 11", "District 23", "District 29", "District 5", "District 9"])
        # District 9's primary box has no "not contested" note: the seat is kept but not classified
        self.assertEqual(r["District 9"]["category"], "unknown")
        self.assertEqual((r["District 1"]["category"], r["District 1"]["majors"]), ("unopposed", "R"))
        self.assertEqual(r["District 1"]["candidates"][0]["name"], "J. Adam Lowe")
        self.assertEqual(r["District 5"]["category"], "two_party")
        self.assertEqual(r["District 11"]["category"], "two_party")  # TBD Democrat still fills the line
        self.assertEqual(r["District 11"]["candidates"][0]["name"], "Bo Watson")
        self.assertEqual((r["District 23"]["category"], r["District 23"]["majors"]), ("one_party", "R"))
        self.assertEqual((r["District 29"]["category"], r["District 29"]["majors"]), ("unopposed", "D"))

    def test_boxes_swatches_and_merge(self):
        with open(os.path.join(os.path.dirname(FIXTURE), "boxes.html")) as f:
            r = {district_key(x["district"]): x for x in parse_page(f.read())}
        self.assertNotIn("106", r)  # special election skipped
        self.assertEqual(r["2"]["candidates"][0]["name"], "Ray Jeffers")  # PA primary table ignored, NC box wins
        # CO swatch-only candidates
        self.assertEqual((r["1"]["category"], r["1"]["majors"]), ("two_party", "DR"))
        self.assertEqual([c["party"] for c in r["1"]["candidates"]], ["D", "R"])
        self.assertEqual((r["10"]["category"], r["10"]["majors"]), ("unopposed", "D"))
        self.assertEqual((r["38"]["category"], r["38"]["majors"]), ("one_party", "D"))  # Libertarian yellow is Other
        # CO row 40 is empty, so the NC-style general box for district 40 wins, not its primary
        self.assertEqual([c["name"] for c in r["40"]["candidates"]], ["Ed Goodwin", "Claude (Dorsey) Harris"])
        self.assertEqual(r["40"]["category"], "two_party")
        # WA: only the general-election rows; write-ins dropped; a TBD slot makes the race unknown
        self.assertEqual([c["name"] for c in r["1 position 1"]["candidates"]], ["Davina Duerr", "Maggie Wang"])
        self.assertEqual(r["1 position 2"]["category"], "unknown")
        # CT: dated primary skipped, district-captioned box read
        self.assertEqual((r["4"]["category"], r["4"]["majors"]), ("unopposed", "D"))

    def test_primary_results(self):
        with open(os.path.join(os.path.dirname(FIXTURE), "primaries.html")) as f:
            r = {district_key(x["district"]): x for x in parse_page(f.read())}
        self.assertEqual(sorted(r), ["1", "2", "3", "5"])  # the "Districts 26–50" box has no district
        # AZ: bold winners of each party's primary make the field; most winners of one party = seats
        self.assertEqual([c["name"] for c in r["1"]["candidates"]], ["Selina Bliss", "Quang Nguyen", "Tara Woods"])
        self.assertEqual((r["1"]["seats"], r["1"]["category"]), (2, "two_party"))
        # HI: only the Democratic primary is shown, so the race is not called unopposed; blank votes dropped
        self.assertEqual((r["2"]["category"], [c["name"] for c in r["2"]["candidates"]]),
                         ("unknown", ["Sue Keohokapu Lee Loy"]))
        # ND: one box per party merges into one district; write-in dropped
        self.assertEqual((r["3"]["seats"], r["3"]["category"], r["3"]["majors"]), (2, "two_party", "DR"))
        # IN: a general box several headings below "District 5" is still read
        self.assertEqual([c["name"] for c in r["5"]["candidates"]], ["Dale DeVon", "Alex Wait"])

    def test_open_primary(self):
        row = ('<tr class="vcard"><td style="background-color:#E81B23"></td><td class="org">{}</td>'
               '<th class="fn"><b>{}</b></th><td>1</td></tr>')
        html = "".join(
            f'<h3>District {d}</h3><table class="wikitable"><caption>Primary election</caption>'
            '<tr><th>Party</th><th>Candidate</th></tr>' + "".join(row.format(p, n) for p, n in cands) + "</table>"
            for d, cands in (("A", [("Republican", "Jeremy Bynum"), ("Independent", "Grant Echohawk")]),
                             ("24", [("Republican", "Ken McCarty"), ("Republican", "Gina Wall")])))
        r = {district_key(x["district"]): x for x in parse_page(html)}
        # Alaska top-four: one primary for every party, so everyone who advances is on the ballot, one seat
        self.assertEqual((r["a"]["seats"], r["a"]["category"], r["a"]["majors"]), (1, "one_party", "R"))
        self.assertEqual((r["24"]["seats"], r["24"]["category"]), (1, "one_party"))

    def test_district_key(self):
        self.assertEqual(district_key("Connecticut's 1st House of Representatives district election, 2026"), "1")
        self.assertEqual(district_key("2026 Maryland House of Delegates District 1A election"), "1a")
        self.assertEqual(district_key("LD 9 (Position 1)"), "9 position 1")
        self.assertEqual(district_key("Addison-1"), "addison 1")
        self.assertIsNone(district_key("Results"))
        self.assertIsNone(district_key("Districts 26–50"))
        self.assertEqual(district_key("District A"), "a")
        self.assertEqual(district_key("District 1 election, Democratic–NPL primary 2 to be nominated"), "1")

    def test_one_candidate_per_row(self):
        r = self.races
        self.assertEqual((r["PA 1"]["category"], r["PA 1"]["majors"]), ("unopposed", "D"))
        self.assertEqual([c["name"] for c in r["PA 3"]["candidates"]], ["Ryan Bizzarro", "Some Challenger"])
        self.assertEqual((r["PA 3"]["seats"], r["PA 3"]["category"]), (1, "two_party"))

    def test_party(self):
        self.assertEqual(party("Republican, Conservative"), "R")
        self.assertEqual(party("Democratic–NPL"), "D")
        self.assertEqual(party("Republican/Democratic"), "R")  # cross-nominated: first named
        self.assertEqual(party("Libertarian"), "O")


if __name__ == "__main__":
    unittest.main()
