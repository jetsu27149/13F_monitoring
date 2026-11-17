#!/usr/bin/env python3
"""Build the static GitHub Pages site into docs/.

The local dashboard reads a ~100 MB dashboard.json and talks to a Python
server. GitHub Pages can do neither: it serves static files, and GitHub
rejects files over 100 MB. This writes a self-contained site:

    docs/index.html, app.js, styles.css   the dashboard front end, in static mode
    docs/snapshot/dashboard.json          the latest quarter, trimmed
    docs/snapshot/stakes.json             recent 13D / 13G / Form 4 filings

Trimming keeps every position of the conviction-tier managers (capped per
book) and the largest positions of the platform and macro books, whose tens
of thousands of rows are most of the file and the least informative part.
Per-manager totals, counts and history are computed from the full data
before trimming, so those figures stay exact.

    python3 scripts/build_pages.py
    git add docs && git commit -m "Publish snapshot" && git push

Then, once: repository Settings -> Pages -> Deploy from a branch -> main, /docs.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
SNAPSHOT = DOCS / "snapshot"
MAX_FILE_MB = 45  # GitHub warns at 50 MB and rejects at 100 MB.
DROP_FIELDS = {"value_thousands"}  # not read by the front end


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the static GitHub Pages site into docs/.")
    parser.add_argument("--conviction-limit", type=int, default=400, help="Positions kept per conviction manager, per book.")
    parser.add_argument("--platform-limit", type=int, default=100, help="Positions kept per platform or macro manager, per book.")
    args = parser.parse_args()

    source = ROOT / "data" / "processed" / "dashboard.json"
    if not source.exists():
        print("data/processed/dashboard.json not found. Run a refresh first.")
        return 1
    dashboard = json.loads(source.read_text(encoding="utf-8"))
    if dashboard.get("metadata", {}).get("mode") == "sample":
        print("The local data is sample data; refusing to publish it as a snapshot.")
        return 1

    tiers = {i["slug"]: i.get("tier", "conviction") for i in json.loads((ROOT / "investors.json").read_text(encoding="utf-8"))}
    limit_for = lambda slug: args.conviction_limit if tiers.get(slug, "conviction") == "conviction" else args.platform_limit

    snapshot = trim(dashboard, limit_for)
    full, kept = len(dashboard["holdings"]), len(snapshot["holdings"])
    report_dates = sorted({i.get("latest_report_date") for i in snapshot["investors"] if i.get("latest_report_date")})
    snapshot["metadata"] = {
        **dashboard["metadata"],
        "snapshot": {
            "built_at": datetime.now(timezone.utc).isoformat(),
            "full_holding_rows": full,
            "kept_holding_rows": kept,
            "conviction_limit": args.conviction_limit,
            "platform_limit": args.platform_limit,
            "note": (
                f"Public snapshot of the latest 13F quarter ({report_dates[-1] if report_dates else 'n/a'}). "
                f"It shows every position of the conviction managers and the top {args.platform_limit} per book for "
                f"platform and macro funds: {kept:,} of {full:,} rows. Totals on the Investors tab use the full filings. "
                "Filings arrive up to 45 days after quarter-end. Research leads, not investment advice."
            ),
        },
    }

    SNAPSHOT.mkdir(parents=True, exist_ok=True)
    write_min(SNAPSHOT / "dashboard.json", snapshot)
    stakes = ROOT / "data" / "processed" / "stakes.json"
    if stakes.exists():
        write_min(SNAPSHOT / "stakes.json", json.loads(stakes.read_text(encoding="utf-8")))
    else:
        print("No stakes.json yet; the Stakes tab will say so.")

    for name in ("app.js", "styles.css"):
        shutil.copyfile(ROOT / "dashboard" / name, DOCS / name)
    (DOCS / "index.html").write_text(static_index(), encoding="utf-8")
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")  # serve files as-is, skip Jekyll

    too_big = []
    print(f"Built docs/ from data generated {dashboard['metadata'].get('generated_at', '?')[:16]}")
    for path in sorted(p for p in DOCS.rglob("*") if p.is_file()):
        size = path.stat().st_size / 1e6
        if size >= 0.05:
            print(f"  {str(path.relative_to(ROOT)):<34}{size:>7.2f} MB")
        if size > MAX_FILE_MB:
            too_big.append(path.name)
    if too_big:
        print(f"Too large for GitHub: {', '.join(too_big)}. Lower --conviction-limit or --platform-limit.")
        return 1
    print(f"Holdings kept: {kept:,} of {full:,}. Next: git add docs && git commit && git push")
    return 0


def trim(dashboard: dict[str, Any], limit_for) -> dict[str, Any]:
    """Keep each manager's largest positions per book, and the change rows that go with them."""
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in dashboard["holdings"]:
        grouped[(row["investor_slug"], row.get("category") or "")].append(row)

    holdings: list[dict[str, Any]] = []
    kept_keys: set[tuple[str, str]] = set()
    for (slug, _), rows in grouped.items():
        rows.sort(key=lambda r: r.get("value_usd") or 0, reverse=True)
        for row in rows[: limit_for(slug)]:
            holdings.append(strip(row))
            kept_keys.add((slug, row["position_key"]))
    holdings.sort(key=lambda r: r.get("value_usd") or 0, reverse=True)

    # Changes: the row for every kept holding, plus each manager's largest
    # exits, which by definition have no current holding to attach to.
    changes: list[dict[str, Any]] = []
    exits: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in dashboard["changes"]:
        key = (row["investor_slug"], row["position_key"])
        if key in kept_keys:
            changes.append(strip(row))
        elif row.get("status") == "exited":
            exits[(row["investor_slug"], row.get("category") or "")].append(row)
    for (slug, _), rows in exits.items():
        rows.sort(key=lambda r: r.get("previous_value_usd") or 0, reverse=True)
        changes.extend(strip(row) for row in rows[: limit_for(slug)])

    return {
        "investors": dashboard["investors"],
        "reports": dashboard["reports"],
        "holdings": holdings,
        "changes": changes,
        "watchlist": dashboard["watchlist"],
    }


def strip(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if k not in DROP_FIELDS}


def write_min(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")


def repo_url() -> str | None:
    try:
        url = subprocess.run(["git", "-C", str(ROOT), "remote", "get-url", "origin"], capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    if url.startswith("git@github.com:"):
        url = "https://github.com/" + url.split(":", 1)[1]
    return url[:-4] if url.endswith(".git") else url or None


def static_index() -> str:
    """dashboard/index.html, switched to static mode and given share metadata."""
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    config = {"dataBase": "./snapshot/", "repoUrl": repo_url()}
    description = "What 37 well-known institutional investors reported holding, from SEC 13F filings: positions, quarter-over-quarter changes, new stakes and a research watchlist."
    head = (
        f'    <meta name="description" content="{description}" />\n'
        '    <meta property="og:title" content="13F Investor Monitor" />\n'
        f'    <meta property="og:description" content="{description}" />\n'
        "  </head>"
    )
    script = f'    <script>window.DASHBOARD_STATIC = {json.dumps(config)};</script>\n    <script src="./app.js"></script>'
    if "  </head>" not in html or '    <script src="./app.js"></script>' not in html:
        raise SystemExit("dashboard/index.html no longer has the markers build_pages.py edits; update static_index().")
    return html.replace("  </head>", head, 1).replace('    <script src="./app.js"></script>', script, 1)


if __name__ == "__main__":
    sys.exit(main())
