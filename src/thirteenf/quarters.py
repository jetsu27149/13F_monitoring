"""One reporting quarter's dashboard, rebuilt from data/raw.

The dashboard's main view uses each manager's latest filing. Picking a quarter
in the Quarter menu rebuilds holdings, changes, investor summaries and the
watchlist as of that report date. The local server does this on request; the
GitHub Pages build does it ahead of time for recent quarters, since a static
site has no server to ask.

Memory stays flat: a manager's filings are read two at a time for holdings
and changes, and history is streamed once, one filing at a time, to draw the
watchlist lifecycle charts. That matters because data/raw holds about a
gigabyte of parsed filings.

Amendments are resolved the same way as in refresh.load_local_rows, so a
13F-HR/A never shows up as an extra quarter.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from thirteenf.analytics import (
    aggregate_positions,
    build_lifecycle_rows,
    build_watchlist,
    change_sort_key,
    compare_positions,
    count_statuses,
    holding_category,
    pattern_summary,
    ratio,
    summarize_report,
    totals_by_category,
    turnover_proxy,
    watchlist_key,
)
from thirteenf.refresh import raw_dir, resolve_amendments


def report_files(root: Path) -> dict[str, dict[str, list[Path]]]:
    """slug -> report_date -> the filing files for that quarter, from filenames only."""
    found: dict[str, dict[str, list[Path]]] = defaultdict(lambda: defaultdict(list))
    base = raw_dir(root)
    if not base.is_dir():
        return {}
    for slug_dir in base.iterdir():
        if not slug_dir.is_dir():
            continue
        for path in slug_dir.glob("*.json"):
            report_date = path.stem.partition("_")[0]
            if report_date:
                found[slug_dir.name][report_date].append(path)
    return {slug: dict(dates) for slug, dates in found.items()}


def load_report(paths: Iterable[Path]) -> list[dict[str, Any]]:
    """Rows for one manager's quarter, with any amendments applied."""
    filings = []
    for path in paths:
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(rows, list) and rows:
            filings.append(rows)
    return resolve_amendments(filings) if filings else []


def available_report_dates(root: Path) -> list[str]:
    """Every report date on disk, newest first."""
    return sorted({d for dates in report_files(root).values() for d in dates}, reverse=True)


def build_quarter(root: Path, report_date: str, base_dashboard: dict[str, Any] | None = None) -> dict[str, Any]:
    return build_quarters(root, [report_date], base_dashboard)[report_date]


def build_quarters(
    root: Path,
    report_dates: list[str],
    base_dashboard: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Build several quarters, sharing one pass over history for the lifecycle charts.

    `base_dashboard` needs only `metadata` and `investors`; pass the loaded
    dashboard to avoid reading the 100 MB file again.
    """
    investors = json.loads((root / "investors.json").read_text(encoding="utf-8"))
    if base_dashboard is None:
        base_dashboard = json.loads((root / "data" / "processed" / "dashboard.json").read_text(encoding="utf-8"))
    base_by_slug = {item.get("slug"): item for item in base_dashboard.get("investors", [])}
    files = report_files(root)

    results: dict[str, dict[str, Any]] = {}
    for report_date in report_dates:
        holdings: list[dict[str, Any]] = []
        changes: list[dict[str, Any]] = []
        summaries: list[dict[str, Any]] = []
        for investor in investors:
            by_date = files.get(investor["slug"], {})
            if report_date not in by_date:
                continue
            dates = sorted(by_date, reverse=True)
            previous_date = next((d for d in dates if d < report_date), None)
            current_rows = load_report(by_date[report_date])
            if not current_rows:
                continue
            previous_rows = load_report(by_date[previous_date]) if previous_date else []
            current_report = report_header(report_date, current_rows)
            previous_report = report_header(previous_date, previous_rows) if previous_rows else None

            current_positions = aggregate_positions(current_rows)
            previous_positions = aggregate_positions(previous_rows)
            current_total = float(sum(p["value_usd"] or 0 for p in current_positions.values()))
            category_totals = totals_by_category(current_positions)
            for position in sorted(current_positions.values(), key=lambda p: p["value_usd"], reverse=True):
                category_total = category_totals[position["category"]]
                holdings.append(
                    {
                        **position,
                        "investor_slug": investor["slug"],
                        "investor": investor["investor"],
                        "manager": investor["manager"],
                        "report_date": report_date,
                        "filing_date": current_report.get("filing_date"),
                        "sec_url": current_report.get("sec_url"),
                        "weight": ratio(position["value_usd"], current_total),
                        "category_weight": ratio(position["value_usd"], category_total),
                        "category_total_usd": category_total,
                    }
                )
            investor_changes = compare_positions(
                investor,
                current_positions,
                previous_positions,
                report_date,
                previous_report.get("report_date") if previous_report else None,
            )
            changes.extend(investor_changes)
            summaries.append(
                investor_summary(
                    investor,
                    base_by_slug.get(investor["slug"], {}),
                    current_rows,
                    previous_rows,
                    current_report,
                    previous_report,
                    investor_changes,
                )
            )

        # Watchlist selection and scores don't depend on history; the
        # lifecycle charts do, and are filled in below in one shared pass.
        watchlist = build_watchlist(holdings, changes, None)
        results[report_date] = {
            "metadata": {
                **base_dashboard.get("metadata", {}),
                "selected_report_date": report_date,
                "selected_holding_rows": len(holdings),
                "selected_change_rows": len(changes),
                "selected_investor_count": len(summaries),
            },
            "investors": sorted(summaries, key=lambda item: item["investor"]),
            "holdings": sorted(holdings, key=lambda item: item["weight"], reverse=True),
            "changes": sorted(changes, key=change_sort_key),
            "watchlist": watchlist,
        }

    attach_lifecycles(results, files, investors)
    return results


def report_header(report_date: str | None, rows: list[dict[str, Any]]) -> dict[str, Any]:
    first = rows[0] if rows else {}
    return {"report_date": report_date, "filing_date": first.get("filing_date"), "sec_url": first.get("sec_url")}


def attach_lifecycles(
    results: dict[str, dict[str, Any]],
    files: dict[str, dict[str, list[Path]]],
    investors: list[dict[str, Any]],
) -> None:
    """Fill each watchlist item's weight history up to its quarter.

    Equivalent to analytics.build_lifecycle_index over every row dated on or
    before the quarter, but it keeps only portfolio totals and the positions
    of watchlist names, streaming one filing at a time.
    """
    keys = {item["position_key"] for payload in results.values() for item in payload["watchlist"]}
    if not keys:
        return
    latest = max(results)
    totals: dict[tuple[str, str], float] = defaultdict(float)
    category_totals: dict[tuple[str, str, str], float] = defaultdict(float)
    positions: dict[tuple[str, str, str], dict[str, float]] = defaultdict(lambda: {"value_usd": 0.0, "shares": 0.0})
    category_of: dict[tuple[str, str], str] = {}
    dates_by_owner: dict[str, set[str]] = defaultdict(set)

    for investor in investors:
        for report_date, paths in files.get(investor["slug"], {}).items():
            if report_date > latest:
                continue
            for row in load_report(paths):
                owner = row.get("investor_slug") or row.get("investor") or ""
                row_date = row.get("report_date")
                if not owner or not row_date:
                    continue
                value = float(row.get("value_usd") or 0)
                category = row.get("category") or holding_category(row)
                dates_by_owner[owner].add(row_date)
                totals[(owner, row_date)] += value
                category_totals[(owner, row_date, category)] += value
                key = watchlist_key(row)
                if key in keys:
                    position = positions[(key, owner, row_date)]
                    position["value_usd"] += value
                    position["shares"] += float(row.get("shares") or 0)
                    category_of[(key, owner)] = category

    pairs = defaultdict(set)
    for key, owner, _ in positions:
        pairs[key].add(owner)

    for report_date, payload in results.items():
        index: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for item in payload["watchlist"]:
            key = item["position_key"]
            for owner in pairs.get(key, ()):
                category = category_of.get((key, owner), "equity")
                points = []
                for date in sorted(d for d in dates_by_owner[owner] if d <= report_date):
                    position = positions.get((key, owner, date), {})
                    value = float(position.get("value_usd") or 0)
                    points.append(
                        {
                            "report_date": date,
                            "value_usd": value,
                            "shares": float(position.get("shares") or 0),
                            "weight": ratio(value, totals[(owner, date)]),
                            "category_weight": ratio(value, category_totals[(owner, date, category)]),
                        }
                    )
                if points:
                    index[(key, owner)] = points
            item["lifecycle"] = build_lifecycle_rows(key, item["owner_details"], index)


def investor_summary(
    investor: dict[str, Any],
    base: dict[str, Any],
    current_rows: list[dict[str, Any]],
    previous_rows: list[dict[str, Any]],
    current_report: dict[str, Any],
    previous_report: dict[str, Any] | None,
    changes: list[dict[str, Any]],
) -> dict[str, Any]:
    report = summarize_report(investor, current_report["report_date"], current_rows)
    previous_summary = summarize_report(investor, previous_report["report_date"], previous_rows) if previous_report else {}
    status_counts = count_statuses(changes)
    turnover = turnover_proxy(changes, report.get("total_value_usd"), previous_summary.get("total_value_usd"))
    concentration_delta = report.get("top_10_concentration", 0) - previous_summary.get("top_10_concentration", 0)
    return {
        "slug": investor["slug"],
        "investor": investor["investor"],
        "manager": investor["manager"],
        "cik": investor["cik"],
        "style": investor.get("style"),
        "notes": investor.get("notes"),
        "dataroma_url": investor.get("dataroma_url"),
        "sec_company_url": f"https://www.sec.gov/edgar/browse/?CIK={int(investor['cik'])}",
        "latest_report_date": report.get("report_date"),
        "latest_filing_date": report.get("filing_date"),
        "latest_sec_url": report.get("sec_url"),
        "total_value_usd": report.get("total_value_usd", 0),
        "equity_value_usd": report.get("equity_value_usd", 0),
        "option_value_usd": report.get("option_value_usd", 0),
        "holding_count": report.get("holding_count", 0),
        "option_count": report.get("option_count", 0),
        "non_option_count": report.get("non_option_count", 0),
        "unique_issuer_count": report.get("unique_issuer_count", 0),
        "unique_non_option_issuer_count": report.get("unique_non_option_issuer_count", 0),
        "top_5_concentration": report.get("top_5_concentration", 0),
        "top_10_concentration": report.get("top_10_concentration", 0),
        "latest_change_counts": status_counts,
        "average_new_positions": base.get("average_new_positions", 0),
        "average_exits": base.get("average_exits", 0),
        "turnover_proxy": turnover,
        "concentration_delta": concentration_delta,
        "parsed_rows": len(current_rows),
        "pattern_summary": pattern_summary(
            report.get("holding_count", 0),
            report.get("top_10_concentration", 0),
            status_counts,
            turnover,
            concentration_delta,
        ),
    }
