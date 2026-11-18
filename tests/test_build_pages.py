"""The static GitHub Pages build: trimming rules and the static index page."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_pages  # noqa: E402


def holding(slug, key, value, category="equity"):
    return {"investor_slug": slug, "position_key": key, "category": category, "value_usd": value, "value_thousands": value / 1000}


def change(slug, key, status, current=0, previous=0, category="equity"):
    return {"investor_slug": slug, "position_key": key, "category": category, "status": status,
            "current_value_usd": current, "previous_value_usd": previous}


class TrimTests(unittest.TestCase):
    def setUp(self):
        self.dashboard = {
            "investors": [{"slug": "conv"}, {"slug": "plat"}],
            "reports": [{"investor_slug": "conv"}],
            "watchlist": [{"position_key": "w"}],
            "holdings": [holding("plat", f"p{i}", 100 - i) for i in range(10)]
            + [holding("plat", f"o{i}", 50 - i, "option") for i in range(5)]
            + [holding("conv", f"c{i}", 10 - i) for i in range(4)],
            "changes": [change("plat", f"p{i}", "held", current=100 - i) for i in range(10)]
            + [change("plat", f"x{i}", "exited", previous=40 - i) for i in range(6)]
            + [change("conv", f"c{i}", "added", current=10 - i) for i in range(4)]
            + [change("conv", "gone", "exited", previous=7)],
        }
        self.snapshot = build_pages.trim(self.dashboard, lambda slug: 3 if slug == "plat" else 400)

    def test_platform_book_keeps_its_largest_rows_per_category(self):
        kept = {(r["investor_slug"], r["position_key"]) for r in self.snapshot["holdings"]}
        self.assertEqual({k for s, k in kept if s == "plat"}, {"p0", "p1", "p2", "o0", "o1", "o2"})

    def test_conviction_book_is_kept_whole(self):
        self.assertEqual(sum(1 for r in self.snapshot["holdings"] if r["investor_slug"] == "conv"), 4)

    def test_changes_follow_kept_holdings_and_include_largest_exits(self):
        keys = {(r["investor_slug"], r["position_key"]) for r in self.snapshot["changes"]}
        self.assertEqual({k for s, k in keys if s == "plat"}, {"p0", "p1", "p2", "x0", "x1", "x2"})
        self.assertIn(("conv", "gone"), keys)

    def test_untrimmed_sections_and_dropped_fields(self):
        self.assertEqual(self.snapshot["watchlist"], self.dashboard["watchlist"])
        self.assertEqual(self.snapshot["investors"], self.dashboard["investors"])
        self.assertTrue(all("value_thousands" not in r for r in self.snapshot["holdings"]))


class StaticIndexTests(unittest.TestCase):
    def test_index_switches_the_app_to_static_mode_before_it_loads(self):
        html = build_pages.static_index()
        self.assertIn("window.DASHBOARD_STATIC", html)
        self.assertLess(html.index("window.DASHBOARD_STATIC"), html.index('src="./app.js"'))
        self.assertIn('"dataBase": "./snapshot/"', html)
        self.assertIn('property="og:title"', html)
        self.assertEqual(html.count('src="./app.js"'), 1)


class PublishQuartersTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(ROOT / "tests"))
        from test_quarters import QuarterTests  # reuse its synthetic filings

        self.fixture = QuarterTests("test_report_dates_are_listed_once_newest_first")
        self.fixture.setUp()
        self.root = self.fixture.root
        self.saved = (build_pages.ROOT, build_pages.QUARTERS_DIR)
        build_pages.ROOT = self.root
        build_pages.QUARTERS_DIR = self.root / "docs" / "snapshot" / "quarters"
        self.dashboard = {"metadata": {"mode": "live"}, "investors": []}
        self.args = argparse.Namespace(quarters=2, force=False, platform_limit=100)

    def tearDown(self):
        build_pages.ROOT, build_pages.QUARTERS_DIR = self.saved
        self.fixture.tearDown()

    def publish(self):
        return build_pages.publish_quarters(self.dashboard, lambda slug: 400, self.args)

    def test_writes_one_trimmed_file_per_quarter(self):
        self.assertEqual(self.publish(), ["2026-06-30", "2026-03-31"])
        q2 = json.loads((build_pages.QUARTERS_DIR / "2026-06-30.json").read_text())
        self.assertEqual(q2["metadata"]["selected_report_date"], "2026-06-30")
        self.assertIn("2026-06-30 quarter", q2["metadata"]["snapshot"]["note"])
        self.assertNotIn("reports", q2)
        self.assertTrue(all("sec_url" not in h and "figi" not in h for h in q2["holdings"]))

    def test_unchanged_quarters_are_not_rebuilt(self):
        self.publish()
        q1 = build_pages.QUARTERS_DIR / "2026-03-31.json"
        q2 = build_pages.QUARTERS_DIR / "2026-06-30.json"
        before = (q1.stat().st_mtime_ns, q2.stat().st_mtime_ns)
        time.sleep(0.05)
        self.publish()
        self.assertEqual(before, (q1.stat().st_mtime_ns, q2.stat().st_mtime_ns))

    def test_a_changed_filing_rebuilds_its_quarter_and_later_ones_only(self):
        self.publish()
        q1 = build_pages.QUARTERS_DIR / "2026-03-31.json"
        q2 = build_pages.QUARTERS_DIR / "2026-06-30.json"
        old = time.time() - 3600
        for raw in (self.root / "data" / "raw").rglob("*.json"):
            os.utime(raw, (old - 3600, old - 3600))  # filings predate the published files
        for f in (q1, q2):
            os.utime(f, (old, old))
        beta_q2 = self.root / "data" / "raw" / "beta" / "2026-06-30_B1.json"
        os.utime(beta_q2, None)  # a Q2 filing changed after the files were written
        self.publish()
        self.assertAlmostEqual(q1.stat().st_mtime, old, delta=1)   # Q1 untouched
        self.assertGreater(q2.stat().st_mtime, old + 60)            # Q2 rebuilt


if __name__ == "__main__":
    unittest.main(verbosity=2)
