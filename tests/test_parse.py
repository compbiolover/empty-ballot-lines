import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))
from build import parse_page, party  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "chamber.html")


class ParseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(FIXTURE) as f:
            cls.races = {r["district"]: r for r in parse_page(f.read())}

    def test_ignores_summary_table_and_finds_all_races(self):
        self.assertEqual(sorted(self.races), sorted([
            "District 1", "District 6", "District 20", "District 28", "District 40",
            "LD 3", "LD 9 (Position 1)", "LD 9 (Position 2)", "LD 12"]))

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

    def test_party(self):
        self.assertEqual(party("Republican, Conservative"), "R")
        self.assertEqual(party("Democratic–NPL"), "D")
        self.assertEqual(party("Republican/Democratic"), "R")  # cross-nominated: first named
        self.assertEqual(party("Libertarian"), "O")


if __name__ == "__main__":
    unittest.main()
