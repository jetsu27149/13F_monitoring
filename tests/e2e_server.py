"""Launch the real dashboard server with the SEC network edge stubbed out.

Used by the browser test: everything except the HTTP calls to sec.gov is the
production code path.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from test_refresh import INFO_TABLE_XML  # noqa: E402


@dataclass
class FakeFiling:
    accession_number: str
    report_date: str
    filing_date: str
    form: str = "13F-HR"
    sec_url: str = "https://www.sec.gov/fake"


class FakeSecClient:
    def __init__(self, cache_dir=None, user_agent=None):
        self.cache_dir = cache_dir
        self.user_agent = user_agent

    def recent_13f_filings(self, cik, limit=4, refresh=False):
        return [
            FakeFiling("0000000001-26-000009", "2026-06-30", "2026-08-14"),
            FakeFiling("0000000001-26-000005", "2026-03-31", "2026-05-15"),
        ]

    def information_table_xml(self, filing, refresh=False):
        return INFO_TABLE_XML, "infotable.xml"


def main() -> int:
    import dashboard_server as ds
    from thirteenf import refresh as rf

    ds.SecClient = FakeSecClient
    rf.SecClient = FakeSecClient

    port = sys.argv[1] if len(sys.argv) > 1 else "8021"
    sys.argv = ["dashboard_server.py", "--port", port, "--no-open"]
    return ds.main()


if __name__ == "__main__":
    raise SystemExit(main())
