"""13D / 13G / Form 4 parsing and the stakes refresh, against fixtures that
mirror the structure of real EDGAR filings (checked Nov 2026)."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from thirteenf.stakes import (  # noqa: E402
    headline_stakes, is_affiliated, manager_brand, parse_form4, parse_schedule_13, refresh_stakes,
)
from test_refresh import FIXTURES, FakeSecClient  # noqa: E402

ALPHA = {"slug": "alpha", "investor": "Alpha Capital", "manager": "ALPHA CAPITAL LP", "cik": "1", "tier": "conviction"}
BETA = {"slug": "beta", "investor": "Beta Partners", "manager": "BETA PARTNERS LLC", "cik": "2", "tier": "platform"}


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


class ParserTests(unittest.TestCase):
    def test_13d_takes_the_largest_reporting_person_and_iso_dates(self):
        r = parse_schedule_13(fixture("schedule_13d.xml"))
        self.assertEqual(r["issuer_name"], "Acme Industrial Corp")
        self.assertEqual(r["issuer_cik"], "0000123456")
        self.assertEqual(r["cusip"], "00123X109")
        self.assertEqual(r["percent"], 7.5)
        self.assertEqual(r["shares"], 4250000)
        self.assertEqual(r["event_date"], "2026-10-28")

    def test_13g_layout_and_lowercase_cik_tag(self):
        r = parse_schedule_13(fixture("schedule_13g.xml"))
        self.assertEqual(r["issuer_name"], "Target Hospitality Corp.")
        self.assertEqual(r["issuer_cik"], "0001712189")
        self.assertEqual(r["percent"], 5.2)
        self.assertEqual(r["shares"], 5046156)
        self.assertEqual(r["event_date"], "2026-11-04")

    def test_placeholder_cusip_becomes_none(self):
        self.assertIsNone(parse_schedule_13(fixture("schedule_13d_own_fund.xml"))["cusip"])

    def test_form4_nets_buys_against_sells(self):
        r = parse_form4(fixture("form4.xml"))
        self.assertEqual(r["ticker"], "WDGT")
        self.assertEqual(r["net_shares"], 80000)
        self.assertAlmostEqual(r["net_value"], 100000 * 25.0 - 20000 * 26.5)
        self.assertEqual(r["owned_after"], 2080000)
        self.assertEqual(r["event_date"], "2026-11-03")


class ClassificationTests(unittest.TestCase):
    def test_brand(self):
        self.assertEqual(manager_brand("THIRD POINT LLC"), "THIRD POINT")
        self.assertEqual(manager_brand("BAUPOST GROUP LLC/MA"), "BAUPOST")
        self.assertEqual(manager_brand("Point72 Asset Management, L.P."), "POINT72")

    def test_own_fund_is_affiliated_outside_stake_is_not(self):
        third_point = {"investor": "Daniel Loeb", "manager": "Third Point LLC"}
        self.assertTrue(is_affiliated("Third Point Private Capital Income Fund", third_point, 100))
        self.assertTrue(is_affiliated("Some Fund", third_point, 100), "majority stake reads as own vehicle")
        self.assertFalse(is_affiliated("Warner Bros Discovery Inc", third_point, 6.1))

    def test_one_word_brand_needs_a_fund_like_issuer(self):
        discovery = {"investor": "Discovery Capital Management", "manager": "DISCOVERY CAPITAL MANAGEMENT, LLC / CT"}
        viking = {"investor": "Viking Global", "manager": "VIKING GLOBAL INVESTORS LP"}
        oaktree = {"investor": "Oaktree Capital Management", "manager": "OAKTREE CAPITAL MANAGEMENT LP"}
        self.assertFalse(is_affiliated("Warner Bros. Discovery, Inc.", discovery, 5.4))
        self.assertFalse(is_affiliated("Viking Therapeutics, Inc.", viking, 6.0))
        self.assertTrue(is_affiliated("Oaktree Specialty Lending Corp", oaktree, 8.0))


class RefreshStakesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        FakeSecClient.instances = []
        self.client = FakeSecClient(cache_dir=self.tmp / "data" / "cache")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_writes_stakes_json_with_flags(self):
        summary = refresh_stakes(client=self.client, investors=[ALPHA], root=self.tmp)
        data = json.loads((self.tmp / "data" / "processed" / "stakes.json").read_text())
        by_file = {r["accession_number"]: r for r in data["filings"]}
        self.assertEqual(summary["stakes_total"], 5)
        self.assertFalse(by_file["0000000001-26-100001"]["affiliated"])
        self.assertTrue(by_file["0000000001-26-100002"]["affiliated"])
        self.assertTrue(by_file["0000000001-26-100004"]["exit"])
        self.assertFalse(by_file["0000000001-26-100003"]["exit"])
        self.assertEqual(by_file["0000000001-26-100005"]["net_shares"], 80000)
        self.assertTrue(by_file["0000000001-26-100001"]["sec_url"].endswith("-index.html"))

    def test_second_run_opens_nothing_new(self):
        refresh_stakes(client=self.client, investors=[ALPHA], root=self.tmp)
        self.client.document_calls.clear()
        summary = refresh_stakes(client=self.client, investors=[ALPHA], root=self.tmp)
        self.assertEqual(summary["stakes_new"], 0)
        self.assertEqual(self.client.document_calls, [])

    def test_form4_inherits_own_fund_flag_from_the_same_issuers_13d(self):
        from unittest import mock
        import thirteenf.stakes as stakes_module
        real = stakes_module.parse_form4

        def form4_on_own_fund(xml_text):
            parsed = real(xml_text)
            parsed["issuer_cik"] = "0002122354"  # the issuer of the own-fund 13D fixture
            parsed["issuer_name"] = "Some Vehicle LP"
            return parsed

        with mock.patch.object(stakes_module, "parse_form4", form4_on_own_fund):
            refresh_stakes(client=self.client, investors=[ALPHA], root=self.tmp)
        records = json.loads((self.tmp / "data" / "processed" / "stakes.json").read_text())["filings"]
        form4 = next(r for r in records if r["kind"] == "4")
        self.assertTrue(form4["affiliated"])

    def test_headlines_drop_amendments_own_funds_and_platform_books(self):
        refresh_stakes(client=self.client, investors=[ALPHA, BETA], root=self.tmp)
        records = json.loads((self.tmp / "data" / "processed" / "stakes.json").read_text())["filings"]
        heads = headline_stakes(records)
        self.assertEqual({(h["investor_slug"], h["issuer_name"]) for h in heads},
                         {("alpha", "Acme Industrial Corp"), ("alpha", "Target Hospitality Corp.")})


if __name__ == "__main__":
    unittest.main(verbosity=2)
