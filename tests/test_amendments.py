"""Original 13F-HR plus 13F-HR/A filings for one quarter must not double-count."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thirteenf.refresh import load_local_rows, resolve_amendments  # noqa: E402


def filing(form, filed, accession, cusips, value=100.0):
    return [
        {"investor_slug": "alpha", "form": form, "filing_date": filed, "accession_number": accession,
         "report_date": "2026-06-30", "cusip": c, "issuer": f"ISSUER {c}", "value_usd": value}
        for c in cusips
    ]


class ResolveAmendmentTests(unittest.TestCase):
    def test_restatement_replaces_the_original(self):
        original = filing("13F-HR", "2026-08-14", "A-1", ["111", "222", "333"], value=100)
        restated = filing("13F-HR/A", "2026-09-02", "A-2", ["111", "222", "333"], value=120)
        rows = resolve_amendments([original, restated])
        self.assertEqual(len(rows), 3, "a restatement must not stack on the original")
        self.assertTrue(all(r["value_usd"] == 120 for r in rows))

    def test_new_holdings_amendment_adds_to_the_original(self):
        original = filing("13F-HR", "2026-08-14", "A-1", ["111", "222", "333", "444"])
        added = filing("13F-HR/A", "2026-08-20", "A-2", ["555"])
        rows = resolve_amendments([original, added])
        self.assertEqual(sorted(r["cusip"] for r in rows), ["111", "222", "333", "444", "555"])

    def test_applied_in_filing_date_order_whatever_the_input_order(self):
        original = filing("13F-HR", "2026-08-14", "A-1", ["111", "222"], value=100)
        restated = filing("13F-HR/A", "2026-09-02", "A-2", ["111", "222"], value=120)
        self.assertTrue(all(r["value_usd"] == 120 for r in resolve_amendments([restated, original])))

    def test_single_filing_passes_through(self):
        only = filing("13F-HR", "2026-08-14", "A-1", ["111"])
        self.assertEqual(resolve_amendments([only]), only)


class LoadLocalRowsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        d = self.tmp / "data" / "raw" / "alpha"
        d.mkdir(parents=True)
        (d / "2026-06-30_A-1.json").write_text(json.dumps(filing("13F-HR", "2026-08-14", "A-1", ["111", "222"])))
        (d / "2026-06-30_A-2.json").write_text(json.dumps(filing("13F-HR/A", "2026-09-02", "A-2", ["111", "222"], 120)))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_quarter_with_an_amendment_on_disk_is_counted_once(self):
        rows, errors = load_local_rows(self.tmp)
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 2)
        self.assertEqual(sum(r["value_usd"] for r in rows), 240)


if __name__ == "__main__":
    unittest.main(verbosity=2)
