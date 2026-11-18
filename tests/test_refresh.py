"""Exercise the incremental refresh path with a stubbed SEC client.

Neither the dev sandbox nor the local VM can reach sec.gov, so the network edge
is faked here. Everything below that edge -- accession bookkeeping, raw-file
writes, the rebuild, and the job state machine -- is the real code.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thirteenf import refresh as refresh_module
from thirteenf.refresh import (
    local_accessions,
    load_local_rows,
    run_incremental_refresh,
    user_agent_looks_unset,
)


@dataclass
class FakeFiling:
    accession_number: str
    report_date: str
    filing_date: str
    form: str = "13F-HR"
    sec_url: str = "https://www.sec.gov/fake"


INVESTORS = [
    {"slug": "alpha", "investor": "Alpha Capital", "manager": "ALPHA CAPITAL LP", "cik": "0000000001"},
    {"slug": "beta", "investor": "Beta Partners", "manager": "BETA PARTNERS LLC", "cik": "0000000002"},
]

INFO_TABLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>MICROSOFT CORP</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>594918104</cusip>
    <value>250000000</value>
    <shrsOrPrnAmt><sshPrnamt>600000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
    <investmentDiscretion>SOLE</investmentDiscretion>
    <votingAuthority><Sole>600000</Sole><Shared>0</Shared><None>0</None></votingAuthority>
  </infoTable>
  <infoTable>
    <nameOfIssuer>AMAZON COM INC</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>023135106</cusip>
    <value>180000000</value>
    <shrsOrPrnAmt><sshPrnamt>900000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
    <investmentDiscretion>SOLE</investmentDiscretion>
    <votingAuthority><Sole>900000</Sole><Shared>0</Shared><None>0</None></votingAuthority>
  </infoTable>
</informationTable>
"""


FIXTURES = Path(__file__).resolve().parent / "fixtures"

# Stake filings each fake investor's index lists, by accession -> fixture file.
STAKE_DOCS = {
    "0000000001-26-100001": ("SCHEDULE 13D", "schedule_13d.xml", 3),
    "0000000001-26-100002": ("SCHEDULE 13D", "schedule_13d_own_fund.xml", 4),
    "0000000001-26-100003": ("SCHEDULE 13G", "schedule_13g.xml", 5),
    "0000000001-26-100004": ("SCHEDULE 13G/A", "schedule_13g_exit.xml", 6),
    "0000000001-26-100005": ("4", "form4.xml", 7),
}


def fake_index(days_ago_offset: int = 0) -> dict:
    """A submissions index with recent stake filings (dates relative to today)."""
    from datetime import date, timedelta

    accessions = list(STAKE_DOCS)
    return {"filings": {"recent": {
        "form": [STAKE_DOCS[a][0] for a in accessions] + ["13F-HR"],
        "accessionNumber": accessions + ["0000000001-26-000009"],
        "filingDate": [(date.today() - timedelta(days=STAKE_DOCS[a][2] + days_ago_offset)).isoformat() for a in accessions] + ["2026-08-14"],
        "primaryDocument": [("xslF345X06/form4.xml" if STAKE_DOCS[a][0] == "4" else "xslSCHEDULE_13D_X02/primary_doc.xml") for a in accessions] + ["primary_doc.xml"],
    }}}


class FakeSecClient:
    """Stands in for SecClient. Records calls so tests can assert on them."""

    instances: list["FakeSecClient"] = []

    def __init__(self, cache_dir=None, user_agent=None):
        self.cache_dir = cache_dir
        self.user_agent = user_agent
        self.filings_calls: list[str] = []
        self.table_calls: list[str] = []
        self.document_calls: list[str] = []
        FakeSecClient.instances.append(self)

    @staticmethod
    def clean_cik(cik):
        return str(cik).zfill(10)

    def submissions(self, cik, refresh=False):
        return fake_index()

    def get_text(self, url, cache_key, refresh=False):
        path = Path(self.cache_dir) / cache_key
        if path.exists() and not refresh:
            return path.read_text(encoding="utf-8")
        accession = Path(cache_key).stem
        self.document_calls.append(accession)
        text = (FIXTURES / STAKE_DOCS[accession][1]).read_text(encoding="utf-8")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return text

    def recent_13f_filings(self, cik, limit=4, refresh=False, **kwargs):
        self.filings_calls.append(cik)
        return [
            FakeFiling("0000000001-26-000009", "2026-06-30", "2026-08-14"),
            FakeFiling("0000000001-26-000005", "2026-03-31", "2026-05-15"),
        ]

    def information_table_xml(self, filing, refresh=False):
        self.table_calls.append(filing.accession_number)
        return INFO_TABLE_XML, "infotable.xml"


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "data" / "raw").mkdir(parents=True)
        (self.tmp / "data" / "processed").mkdir(parents=True)
        (self.tmp / "investors.json").write_text(json.dumps(INVESTORS), encoding="utf-8")

        # Seed one already-downloaded quarter so only the newer one is missing.
        for investor in INVESTORS:
            seeded = self.tmp / "data" / "raw" / investor["slug"] / "2026-03-31_0000000001-26-000005.json"
            seeded.parent.mkdir(parents=True, exist_ok=True)
            seeded.write_text(
                json.dumps(
                    [
                        {
                            "investor_slug": investor["slug"],
                            "investor": investor["investor"],
                            "manager": investor["manager"],
                            "cik": investor["cik"],
                            "accession_number": "0000000001-26-000005",
                            "form": "13F-HR",
                            "filing_date": "2026-05-15",
                            "report_date": "2026-03-31",
                            "issuer": "MICROSOFT CORP",
                            "title_of_class": "COM",
                            "cusip": "594918104",
                            "value_usd": 200000000,
                            "value_thousands": 200000,
                            "shares": 500000,
                            "share_type": "SH",
                            "put_call": None,
                        }
                    ]
                ),
                encoding="utf-8",
            )

        FakeSecClient.instances = []
        self._real_client = refresh_module.SecClient
        refresh_module.SecClient = FakeSecClient

    def tearDown(self):
        refresh_module.SecClient = self._real_client
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_accessions_read_from_filenames(self):
        found = local_accessions(self.tmp)
        self.assertEqual(found["alpha"], {"0000000001-26-000005"})
        self.assertEqual(found["beta"], {"0000000001-26-000005"})

    def test_downloads_only_the_missing_quarter(self):
        progress_log: list[tuple[float, str]] = []
        result = run_incremental_refresh(
            root=self.tmp,
            investors=INVESTORS,
            user_agent="test agent test@example.com",
            quarters=4,
            progress=lambda f, m: progress_log.append((f, m)),
        )

        # Only the 2026-06-30 filing was missing, for each of the two investors.
        self.assertEqual(result["filings_added"], 2)
        self.assertTrue(result["rebuilt"])
        pulled = [call for client in FakeSecClient.instances for call in client.table_calls]
        self.assertEqual(sorted(pulled), ["0000000001-26-000009", "0000000001-26-000009"])
        self.assertNotIn("0000000001-26-000005", pulled, "already-stored filing should not be re-downloaded")

        # New raw files landed where refresh_data.py would have put them.
        for investor in INVESTORS:
            written = self.tmp / "data" / "raw" / investor["slug"] / "2026-06-30_0000000001-26-000009.json"
            self.assertTrue(written.exists(), f"missing raw file for {investor['slug']}")

        # Outputs were rebuilt.
        dashboard = json.loads((self.tmp / "data" / "processed" / "dashboard.json").read_text())
        self.assertIn("holdings", dashboard)
        self.assertTrue((self.tmp / "data" / "processed" / "holdings.csv").stat().st_size > 0)
        self.assertTrue((self.tmp / "data" / "processed" / "watchlist.csv").exists())

        # Progress moved forward and finished.
        self.assertTrue(progress_log)
        self.assertEqual(progress_log[-1][0], 1.0)

    def test_second_run_is_a_no_op(self):
        run_incremental_refresh(
            root=self.tmp, investors=INVESTORS, user_agent="ua test@example.com", quarters=4
        )
        FakeSecClient.instances = []
        result = run_incremental_refresh(
            root=self.tmp, investors=INVESTORS, user_agent="ua test@example.com", quarters=4
        )
        self.assertEqual(result["filings_added"], 0)
        self.assertFalse(result["rebuilt"], "nothing new means no expensive rebuild")
        pulled = [call for client in FakeSecClient.instances for call in client.table_calls]
        self.assertEqual(pulled, [], "no information tables should be fetched when nothing is new")

    def test_rebuild_covers_every_investor_not_just_the_refreshed_one(self):
        # Refresh only alpha; beta must still be present in the rebuilt output.
        run_incremental_refresh(
            root=self.tmp, investors=[INVESTORS[0]], user_agent="ua test@example.com", quarters=4
        )
        dashboard = json.loads((self.tmp / "data" / "processed" / "dashboard.json").read_text())
        slugs = {item.get("slug") for item in dashboard.get("investors", [])}
        self.assertIn("beta", slugs, "rebuilding from a subset must not drop other investors")

    def test_broken_raw_file_does_not_abort_the_run(self):
        bad = self.tmp / "data" / "raw" / "alpha" / "2026-01-01_0000000001-26-000001.json"
        bad.write_text("{not json", encoding="utf-8")
        rows, errors = load_local_rows(self.tmp)
        self.assertTrue(errors, "a corrupt raw file should be reported")
        self.assertTrue(rows, "other files should still load")

    def test_placeholder_user_agent_is_detected(self):
        self.assertTrue(user_agent_looks_unset("13F Monitoring local dashboard contact@example.com"))
        self.assertTrue(user_agent_looks_unset(""))
        self.assertFalse(user_agent_looks_unset("13F Monitoring jay@realdomain.com"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
