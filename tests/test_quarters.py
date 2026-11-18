"""Rebuilding one quarter from data/raw (thirteenf.quarters)."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thirteenf.quarters import available_report_dates, build_quarter, build_quarters  # noqa: E402

INVESTORS = [
    {"slug": "alpha", "investor": "Alpha Capital", "manager": "ALPHA CAPITAL LP", "cik": "1", "tier": "conviction"},
    {"slug": "beta", "investor": "Beta Partners", "manager": "BETA PARTNERS LLC", "cik": "2", "tier": "conviction"},
]


def row(slug, report_date, cusip, issuer, value, shares, accession, form="13F-HR", filed=None):
    return {
        "investor_slug": slug, "investor": slug.title(), "manager": slug.upper(), "cik": "1",
        "accession_number": accession, "form": form, "filing_date": filed or f"{report_date[:4]}-{int(report_date[5:7]) % 12 + 1:02d}-14",
        "report_date": report_date, "issuer": issuer, "title_of_class": "COM", "cusip": cusip,
        "value_usd": value, "value_reported": value, "value_scale": 1, "shares": shares, "share_type": "SH", "put_call": None,
    }


class QuarterTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "investors.json").write_text(json.dumps(INVESTORS))
        (self.root / "data" / "processed").mkdir(parents=True)
        (self.root / "data" / "processed" / "dashboard.json").write_text(json.dumps({"metadata": {"mode": "live"}, "investors": []}))
        self.write("alpha", "2026-03-31", "A1", [row("alpha", "2026-03-31", "111", "AAA CORP", 100, 10, "A1"), row("alpha", "2026-03-31", "222", "BBB CORP", 100, 10, "A1")])
        self.write("alpha", "2026-06-30", "A2", [row("alpha", "2026-06-30", "111", "AAA CORP", 300, 30, "A2")])
        # A restatement of Q2 filed later: must replace A2, not stack on it or count as a quarter.
        self.write("alpha", "2026-06-30", "A3", [row("alpha", "2026-06-30", "111", "AAA CORP", 300, 30, "A3", "13F-HR/A", "2026-09-02"),
                                                 row("alpha", "2026-06-30", "333", "CCC CORP", 100, 5, "A3", "13F-HR/A", "2026-09-02")])
        self.write("beta", "2026-06-30", "B1", [row("beta", "2026-06-30", "333", "CCC CORP", 50, 2, "B1")])

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, slug, report_date, accession, rows):
        d = self.root / "data" / "raw" / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{report_date}_{accession}.json").write_text(json.dumps(rows))

    def test_report_dates_are_listed_once_newest_first(self):
        self.assertEqual(available_report_dates(self.root), ["2026-06-30", "2026-03-31"])

    def test_amended_quarter_is_counted_once_and_compared_with_the_prior_quarter(self):
        q = build_quarter(self.root, "2026-06-30")
        alpha = [h for h in q["holdings"] if h["investor_slug"] == "alpha"]
        self.assertEqual(sorted(h["cusip"] for h in alpha), ["111", "333"])
        self.assertEqual(sum(h["value_usd"] for h in alpha), 400)
        statuses = {c["cusip"]: c["status"] for c in q["changes"] if c["investor_slug"] == "alpha"}
        self.assertEqual(statuses, {"111": "added", "222": "exited", "333": "new"})
        self.assertEqual({c["previous_report_date"] for c in q["changes"] if c["investor_slug"] == "alpha"}, {"2026-03-31"})

    def test_only_managers_that_filed_that_quarter_appear(self):
        q = build_quarter(self.root, "2026-03-31")
        self.assertEqual([i["slug"] for i in q["investors"]], ["alpha"])
        self.assertEqual(q["metadata"]["selected_report_date"], "2026-03-31")

    def test_lifecycle_history_stops_at_the_selected_quarter(self):
        quarters = build_quarters(self.root, ["2026-06-30", "2026-03-31"])
        q2 = {w["cusip"]: w for w in quarters["2026-06-30"]["watchlist"]}
        points = q2["111"]["lifecycle"][0]["points"]
        self.assertEqual([p["report_date"] for p in points], ["2026-03-31", "2026-06-30"])
        self.assertAlmostEqual(points[0]["weight"], 0.5)   # 100 of 200 in Q1
        self.assertAlmostEqual(points[1]["weight"], 0.75)  # 300 of 400 in Q2, after the restatement
        q1 = {w["cusip"]: w for w in quarters["2026-03-31"]["watchlist"]}
        for item in q1.values():
            for life in item["lifecycle"]:
                self.assertTrue(all(p["report_date"] <= "2026-03-31" for p in life["points"]))

    def test_shared_ownership_across_managers(self):
        q = build_quarter(self.root, "2026-06-30")
        ccc = next(w for w in q["watchlist"] if w["cusip"] == "333")
        self.assertEqual(sorted(ccc["owners"]), ["Alpha Capital", "Beta Partners"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
