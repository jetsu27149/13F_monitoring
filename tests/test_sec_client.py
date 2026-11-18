"""SecClient.recent_13f_filings: keeping every filing of a quarter when asked."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thirteenf.sec_client import SecClient  # noqa: E402

INDEX = {"filings": {"recent": {
    "form":            ["13F-HR",     "13F-HR/A",   "13F-HR",     "4",          "13F-HR",     "13F-HR"],
    "accessionNumber": ["A-5",        "A-4",        "A-3",        "X-1",        "A-2",        "A-1"],
    "filingDate":      ["2025-05-15", "2025-04-16", "2025-02-14", "2025-02-01", "2024-11-14", "2024-08-14"],
    "reportDate":      ["2025-03-31", "2024-12-31", "2024-12-31", "",           "2024-09-30", "2024-06-30"],
    "primaryDocument": ["d.xml"] * 6,
}}}


class RecentFilingsTests(unittest.TestCase):
    def setUp(self):
        self.client = SecClient(cache_dir=Path("/nonexistent"), user_agent="test test@example.org")
        self.client.submissions = lambda cik, refresh=False: INDEX

    def test_default_keeps_the_newest_filing_per_period(self):
        filings = self.client.recent_13f_filings("1", limit=3)
        self.assertEqual([f.accession_number for f in filings], ["A-5", "A-4", "A-2"])

    def test_all_filings_mode_keeps_the_original_behind_an_amendment(self):
        filings = self.client.recent_13f_filings("1", limit=3, latest_per_period=False)
        self.assertEqual([f.accession_number for f in filings], ["A-5", "A-4", "A-3", "A-2"])

    def test_limit_counts_report_periods_not_filings(self):
        filings = self.client.recent_13f_filings("1", limit=2, latest_per_period=False)
        self.assertEqual({f.report_date for f in filings}, {"2025-03-31", "2024-12-31"})
        self.assertEqual(len(filings), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
