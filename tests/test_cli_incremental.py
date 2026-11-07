"""The command-line --incremental refresh, with the SEC network edge stubbed."""

from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import refresh_data  # noqa: E402
from thirteenf import refresh as refresh_module  # noqa: E402
from test_refresh import FakeSecClient, INVESTORS  # noqa: E402


class IncrementalCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "data" / "processed").mkdir(parents=True)
        (self.tmp / "investors.json").write_text(json.dumps(INVESTORS), encoding="utf-8")
        self._root, self._client = refresh_data.ROOT, refresh_module.SecClient
        self._argv, self._ua = sys.argv, os.environ.pop("SEC_USER_AGENT", None)
        refresh_data.ROOT = self.tmp
        refresh_module.SecClient = FakeSecClient
        FakeSecClient.instances = []

    def tearDown(self):
        refresh_data.ROOT, refresh_module.SecClient, sys.argv = self._root, self._client, self._argv
        os.environ.pop("SEC_USER_AGENT", None)
        if self._ua is not None:
            os.environ["SEC_USER_AGENT"] = self._ua
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cli(self, *extra):
        sys.argv = ["refresh_data.py", "--investors", str(self.tmp / "investors.json"), "--incremental", *extra]
        out = io.StringIO()
        with redirect_stdout(out):
            code = refresh_data.main()
        return code, out.getvalue()

    def test_reads_user_agent_from_dotenv_and_downloads(self):
        (self.tmp / ".env").write_text('SEC_USER_AGENT="test-agent test@example.org"\n', encoding="utf-8")
        code, out = self.run_cli()
        self.assertEqual(code, 0, out)
        self.assertIn("Filings added: 4", out)  # two quarters x two investors, none on disk yet
        self.assertEqual({c.user_agent for c in FakeSecClient.instances}, {"test-agent test@example.org"})
        self.assertTrue((self.tmp / "data" / "processed" / "dashboard.json").exists())

    def test_second_run_finds_nothing_and_leaves_dashboard_alone(self):
        (self.tmp / ".env").write_text('SEC_USER_AGENT="test-agent test@example.org"\n', encoding="utf-8")
        self.run_cli()
        before = (self.tmp / "data" / "processed" / "dashboard.json").stat().st_mtime_ns
        code, out = self.run_cli()
        self.assertEqual(code, 0)
        self.assertIn("No new 13F filings", out)
        self.assertNotIn("Stake filings skipped", out)
        self.assertEqual(before, (self.tmp / "data" / "processed" / "dashboard.json").stat().st_mtime_ns)

    def test_refuses_to_run_with_placeholder_user_agent(self):
        code, out = self.run_cli()
        self.assertEqual(code, 2)
        self.assertIn("SEC_USER_AGENT is not set", out)
        self.assertEqual(FakeSecClient.instances, [], "must not contact SEC with the placeholder agent")


if __name__ == "__main__":
    unittest.main(verbosity=2)
