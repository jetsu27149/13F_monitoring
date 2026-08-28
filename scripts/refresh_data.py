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
from thirteenf.refresh import flatten_row, write_csv, write_json
from thirteenf.sample_data import generate_sample_holdings
from thirteenf.sec_client import SecClient, SecClientError


DEFAULT_USER_AGENT = "13F Monitoring local dashboard contact@example.com"


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh 13F dashboard data from SEC EDGAR.")
    parser.add_argument("--investors", default=ROOT / "investors.json", type=Path)
    parser.add_argument("--quarters", default=20, type=int, help="Number of recent report periods per investor.")
    parser.add_argument("--refresh-cache", action="store_true", help="Re-fetch SEC responses even when cached.")
    parser.add_argument("--sample", action="store_true", help="Generate deterministic demo data instead of live SEC data.")
    parser.add_argument("--allow-empty", action="store_true", help="Write an empty dashboard when no rows are fetched.")
    parser.add_argument("--out", default=ROOT / "data" / "processed" / "dashboard.json", type=Path)
    parser.add_argument("--user-agent", default=os.environ.get("SEC_USER_AGENT", DEFAULT_USER_AGENT))
    args = parser.parse_args()

    investors = load_investors(args.investors)
    errors: list[str] = []

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


def fetch_holdings(investors: list[dict[str, Any]], args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[str]]:
    client = SecClient(
        cache_dir=ROOT / "data" / "cache",
        user_agent=args.user_agent,
    )
    holdings: list[dict[str, Any]] = []
    errors: list[str] = []

    for investor in investors:
        try:
            filings = client.recent_13f_filings(
                investor["cik"],
                limit=args.quarters,
                refresh=args.refresh_cache,
            )
        except (SecClientError, OSError) as exc:
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
