#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thirteenf.analytics import build_dashboard_data
from thirteenf.parser import parse_information_table
from thirteenf.refresh import (
    flatten_row,
    investors_all,
    load_env_file,
    load_local_rows,
    rebuild_outputs,
    run_incremental_refresh,
    user_agent_looks_unset,
    write_csv,
    write_json,
)
from thirteenf.sample_data import generate_sample_holdings
from thirteenf.sec_client import SecClient, SecClientError


DEFAULT_USER_AGENT = "13F Monitoring local dashboard contact@example.com"


def main() -> int:
    # Before argument parsing: --user-agent's default reads SEC_USER_AGENT, and a
    # scheduled job has no shell profile, so .env is the only place it can come from.
    load_env_file(ROOT / ".env")

    parser = argparse.ArgumentParser(description="Refresh 13F dashboard data from SEC EDGAR.")
    parser.add_argument("--investors", default=ROOT / "investors.json", type=Path)
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Download only filings missing from data/raw, then rebuild. The same path as the dashboard's "
        "Check filings button; needs no server or browser, so it suits a scheduled job.",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Rebuild the dashboard from filings already in data/raw without contacting SEC.",
    )
    parser.add_argument(
        "--quarters",
        default=None,
        type=int,
        help="Recent report periods per investor (default 20 for a full pull, 4 for --incremental).",
    )
    parser.add_argument("--refresh-cache", action="store_true", help="Re-fetch SEC responses even when cached.")
    parser.add_argument("--sample", action="store_true", help="Generate deterministic demo data instead of live SEC data.")
    parser.add_argument("--allow-empty", action="store_true", help="Write an empty dashboard when no rows are fetched.")
    parser.add_argument("--out", default=ROOT / "data" / "processed" / "dashboard.json", type=Path)
    parser.add_argument("--user-agent", default=os.environ.get("SEC_USER_AGENT", DEFAULT_USER_AGENT))
    args = parser.parse_args()

    investors = load_investors(args.investors)
    errors: list[str] = []

    if args.rebuild:
        return run_rebuild()
    if args.incremental:
        return run_incremental(investors, args)
    if args.quarters is None:
        args.quarters = 20

    if args.sample:
        holdings = generate_sample_holdings(investors)
        mode = "sample"
    else:
        holdings, errors = fetch_holdings(investors, args)
        mode = "live"

    if not holdings and not args.allow_empty:
        print("No holding rows were fetched; existing dashboard output was left unchanged.")
        if errors:
            print("Warnings:")
            for error in errors:
                print(f"- {error}")
        return 1

    dashboard = build_dashboard_data(investors, holdings, mode=mode, errors=errors)
    write_json(args.out, dashboard)
    write_csv(ROOT / "data" / "processed" / "holdings.csv", dashboard["holdings"])
    write_csv(ROOT / "data" / "processed" / "changes.csv", dashboard["changes"])
    write_csv(ROOT / "data" / "processed" / "watchlist.csv", dashboard["watchlist"])

    print(f"Mode: {mode}")
    print(f"Investors: {len(investors)}")
    print(f"Parsed holding rows: {len(holdings)}")
    print(f"Latest holdings: {len(dashboard['holdings'])}")
    print(f"Watchlist candidates: {len(dashboard['watchlist'])}")
    print(f"Wrote: {args.out}")
    if errors:
        print("Warnings:")
        for error in errors:
            print(f"- {error}")
    return 0 if holdings else 1


def run_rebuild() -> int:
    """Regenerate dashboard.json and the CSVs from data/raw. No network."""
    rows, errors = load_local_rows(ROOT)
    if not rows:
        print("No filings found under data/raw; nothing to rebuild.")
        return 1
    dashboard = rebuild_outputs(ROOT, investors_all(ROOT, []), rows, errors=errors)
    print(f"Rebuilt from {len(rows)} holding rows: {len(dashboard['holdings'])} latest holdings, "
          f"{len(dashboard['watchlist'])} watchlist names.")
    for error in errors:
        print(f"  - {error}")
    return 0


def run_incremental(investors: list[dict[str, Any]], args: argparse.Namespace) -> int:
    """Command-line twin of the dashboard's Check filings button."""
    if user_agent_looks_unset(args.user_agent):
        print(
            "SEC_USER_AGENT is not set. SEC rejects clients without a working contact address.\n"
            'Add SEC_USER_AGENT="13F Monitoring local dashboard <your email>" to .env and rerun.'
        )
        return 2

    quarters = args.quarters or 4
    last = {"message": ""}

    def progress(fraction: float, message: str) -> None:
        if message != last["message"]:
            last["message"] = message
            print(f"[{fraction:>4.0%}] {message}", flush=True)

    summary = run_incremental_refresh(
        root=ROOT,
        investors=investors,
        user_agent=args.user_agent,
        quarters=quarters,
        progress=progress,
    )

    downloaded = summary.get("downloaded", [])
    print(f"\nFilings added: {len(downloaded)}")
    for item in sorted(downloaded, key=lambda d: (d["report_date"], d.get("investor") or "")):
        print(f"  {item['report_date']}  {item.get('investor')}  ({item['rows']} rows, filed {item['filing_date']})")
    if summary.get("rebuilt"):
        print(f"Dashboard rebuilt: {summary.get('holdings')} latest holdings, {summary.get('watchlist')} watchlist names.")
    else:
        print("No new 13F filings; dashboard holdings left unchanged.")
    print_stakes(summary)
    problems = summary.get("errors", [])
    if problems:
        print(f"\nWarnings ({len(problems)}):")
        for problem in problems:
            print(f"  - {problem}")
    # Per-investor problems are normal mid-season; only fail when nothing worked at all.
    return 1 if problems and not downloaded and len(problems) >= len(investors) else 0


def print_stakes(summary: dict[str, Any]) -> None:
    """Summarise the 13D/13G/Form 4 step, leading with outside stakes by conviction managers."""
    from thirteenf.stakes import headline_stakes

    if summary.get("stakes_total") is None:
        return
    print(f"\nStake filings (13D/13G/Form 4, last 90 days): {summary['stakes_total']}, {summary.get('stakes_new', 0)} newly opened.")
    path = ROOT / "data" / "processed" / "stakes.json"
    try:
        records = json.loads(path.read_text(encoding="utf-8")).get("filings", [])
    except (OSError, ValueError):
        return
    headlines = headline_stakes(records)[:10]
    if headlines:
        print("Newest outside stakes by conviction managers:")
        for r in headlines:
            pct = f"{r['percent']:.1f}%" if r.get("percent") is not None else "?"
            flag = "  (dropped to 5% or less)" if r.get("exit") else ""
            print(f"  {r['filing_date']}  {r['form']:<13} {r.get('investor', '')[:24]:<25} {str(r.get('issuer_name'))[:38]:<39} {pct}{flag}")


def fetch_holdings(investors: list[dict[str, Any]], args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[str]]:
    client = SecClient(
        cache_dir=ROOT / "data" / "cache",
        user_agent=args.user_agent,
    )
    holdings: list[dict[str, Any]] = []
    errors: list[str] = []

    for investor in investors:
        try:
            # Always re-fetch the submissions index: it is one small file per
            # investor, and a cached copy silently hides every filing made since.
            filings = client.recent_13f_filings(investor["cik"], limit=args.quarters, refresh=True)
        except (SecClientError, OSError) as exc:
            try:
                filings = client.recent_13f_filings(investor["cik"], limit=args.quarters, refresh=False)
                errors.append(f"{investor['investor']}: SEC unreachable ({exc}); used cached filing list.")
            except (SecClientError, OSError, ValueError):
                errors.append(f"{investor['investor']}: could not load submissions: {exc}")
                continue

        if not filings:
            errors.append(f"{investor['investor']}: no recent 13F filings found.")
            continue

        for filing in filings:
            try:
                xml_text, info_table_file = client.information_table_xml(filing, refresh=args.refresh_cache)
                parsed_rows = parse_information_table(xml_text)
            except (SecClientError, OSError, ValueError) as exc:
                errors.append(f"{investor['investor']} {filing.report_date}: could not parse filing: {exc}")
                continue

            raw_path = ROOT / "data" / "raw" / investor["slug"] / f"{filing.report_date}_{filing.accession_number}.json"
            raw_rows = []
            for row in parsed_rows:
                enriched = {
                    "investor_slug": investor["slug"],
                    "investor": investor["investor"],
                    "manager": investor["manager"],
                    "cik": investor["cik"],
                    "accession_number": filing.accession_number,
                    "form": filing.form,
                    "filing_date": filing.filing_date,
                    "report_date": filing.report_date,
                    "information_table_file": info_table_file,
                    "sec_url": filing.sec_url,
                    **row,
                }
                holdings.append(enriched)
                raw_rows.append(enriched)
            write_json(raw_path, raw_rows)

    return holdings, errors


def load_investors(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
