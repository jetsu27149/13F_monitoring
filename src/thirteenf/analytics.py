from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any


def build_dashboard_data(
    investors: list[dict[str, Any]],
    holdings: list[dict[str, Any]],
    *,
    mode: str,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    errors = errors or []
    investors_by_slug = {investor["slug"]: investor for investor in investors}
    rows_by_investor: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in holdings:
        rows_by_investor[row["investor_slug"]].append(row)

    investor_summaries: list[dict[str, Any]] = []
    latest_holdings: list[dict[str, Any]] = []
    latest_changes: list[dict[str, Any]] = []
    all_report_summaries: list[dict[str, Any]] = []

    for slug, investor in investors_by_slug.items():
        investor_rows = rows_by_investor.get(slug, [])
        by_report = group_by(investor_rows, "report_date")
        report_dates = sorted(by_report.keys(), reverse=True)
        report_summaries = [
            summarize_report(investor, report_date, by_report[report_date])
            for report_date in report_dates
        ]
        all_report_summaries.extend(report_summaries)

        latest_report = report_dates[0] if report_dates else None
        previous_report = report_dates[1] if len(report_dates) > 1 else None
        latest_rows = by_report.get(latest_report, []) if latest_report else []
        previous_rows = by_report.get(previous_report, []) if previous_report else []

        current_positions = aggregate_positions(latest_rows)
        previous_positions = aggregate_positions(previous_rows)
        total_current = sum_number(position["value_usd"] for position in current_positions.values())
        current_category_totals = totals_by_category(current_positions)

        for position in sorted(current_positions.values(), key=lambda item: item["value_usd"], reverse=True):
            category_total = current_category_totals[position["category"]]
            latest_holdings.append(
                {
                    **position,
                    "investor_slug": slug,
                    "investor": investor["investor"],
                    "manager": investor["manager"],
                    "report_date": latest_report,
                    "filing_date": first_value(latest_rows, "filing_date"),
                    "sec_url": first_value(latest_rows, "sec_url"),
                    "weight": ratio(position["value_usd"], total_current),
                    "category_weight": ratio(position["value_usd"], category_total),
                    "category_total_usd": category_total,
                }
            )

        changes = compare_positions(
            investor,
            current_positions,
            previous_positions,
            latest_report,
            previous_report,
        )
        latest_changes.extend(changes)

        history_changes = []
        for index in range(len(report_dates) - 1):
            history_changes.append(
                compare_positions(
                    investor,
                    aggregate_positions(by_report[report_dates[index]]),
                    aggregate_positions(by_report[report_dates[index + 1]]),
                    report_dates[index],
                    report_dates[index + 1],
                )
            )

        investor_summaries.append(
            build_investor_summary(
                investor,
                report_summaries,
                changes,
                history_changes,
                len(investor_rows),
            )
        )

    watchlist = build_watchlist(latest_holdings, latest_changes, holdings)

    return {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "source": "SEC EDGAR 13F filings",
            "investor_count": len(investors),
            "holding_rows": len(holdings),
            "latest_holding_rows": len(latest_holdings),
            "errors": errors,
            "caveats": [
                "13F filings are delayed and usually arrive up to 45 days after quarter-end.",
                "13F data excludes shorts, cash, many non-US holdings, private investments, and most macro exposure.",
                "Recent SEC 13F XML market values are reported in dollars; older pre-2023 filings may need separate normalization.",
                "Recommendations are research prompts, not financial advice.",
            ],
        },
        "investors": sorted(investor_summaries, key=lambda item: item["investor"]),
        "reports": sorted(
            all_report_summaries,
            key=lambda item: (item["report_date"] or "", item["investor"]),
            reverse=True,
        ),
        "holdings": sorted(latest_holdings, key=lambda item: item["weight"], reverse=True),
        "changes": sorted(latest_changes, key=change_sort_key),
        "watchlist": watchlist,
    }


def summarize_report(
    investor: dict[str, Any],
    report_date: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    positions = aggregate_positions(rows)
    total_value = sum_number(position["value_usd"] for position in positions.values())
    category_totals = totals_by_category(positions)
    top_values = sorted((position["value_usd"] for position in positions.values()), reverse=True)
    option_rows = [row for row in rows if holding_category(row) == "option"]
    non_option_rows = [row for row in rows if holding_category(row) == "equity"]
    return {
        "investor_slug": investor["slug"],
        "investor": investor["investor"],
        "manager": investor["manager"],
        "report_date": report_date,
        "filing_date": first_value(rows, "filing_date"),
        "form": first_value(rows, "form"),
        "sec_url": first_value(rows, "sec_url"),
        "total_value_usd": total_value,
        "equity_value_usd": category_totals["equity"],
        "option_value_usd": category_totals["option"],
        "holding_count": len(positions),
        "option_count": len(option_rows),
        "non_option_count": len(non_option_rows),
        "unique_issuer_count": len({(row.get("issuer") or "").upper() for row in rows if row.get("issuer")}),
        "unique_non_option_issuer_count": len(
            {(row.get("issuer") or "").upper() for row in non_option_rows if row.get("issuer")}
        ),
        "top_5_concentration": ratio(sum(top_values[:5]), total_value),
        "top_10_concentration": ratio(sum(top_values[:10]), total_value),
    }


def build_investor_summary(
    investor: dict[str, Any],
    report_summaries: list[dict[str, Any]],
    latest_changes: list[dict[str, Any]],
    history_changes: list[list[dict[str, Any]]],
    parsed_rows: int,
) -> dict[str, Any]:
    latest = report_summaries[0] if report_summaries else {}
    oldest = report_summaries[-1] if report_summaries else {}
    status_counts = count_statuses(latest_changes)
    historical_counts = [count_statuses(changes) for changes in history_changes]

    average_new = average(count.get("new", 0) for count in historical_counts)
    average_exited = average(count.get("exited", 0) for count in historical_counts)
    latest_turnover = turnover_proxy(latest_changes, latest.get("total_value_usd"), oldest.get("total_value_usd"))
    concentration_delta = (
        latest.get("top_10_concentration", 0) - oldest.get("top_10_concentration", 0)
        if latest and oldest
        else 0
    )

    return {
        "slug": investor["slug"],
        "investor": investor["investor"],
        "manager": investor["manager"],
        "cik": investor["cik"],
        "style": investor.get("style"),
        "notes": investor.get("notes"),
        "dataroma_url": investor.get("dataroma_url"),
        "sec_company_url": f"https://www.sec.gov/edgar/browse/?CIK={int(investor['cik'])}",
        "latest_report_date": latest.get("report_date"),
        "latest_filing_date": latest.get("filing_date"),
        "latest_sec_url": latest.get("sec_url"),
        "total_value_usd": latest.get("total_value_usd", 0),
        "equity_value_usd": latest.get("equity_value_usd", 0),
        "option_value_usd": latest.get("option_value_usd", 0),
        "holding_count": latest.get("holding_count", 0),
        "option_count": latest.get("option_count", 0),
        "non_option_count": latest.get("non_option_count", 0),
        "unique_issuer_count": latest.get("unique_issuer_count", 0),
        "unique_non_option_issuer_count": latest.get("unique_non_option_issuer_count", 0),
        "top_5_concentration": latest.get("top_5_concentration", 0),
        "top_10_concentration": latest.get("top_10_concentration", 0),
        "latest_change_counts": status_counts,
        "average_new_positions": average_new,
        "average_exits": average_exited,
        "turnover_proxy": latest_turnover,
        "concentration_delta": concentration_delta,
        "parsed_rows": parsed_rows,
        "pattern_summary": pattern_summary(
            latest.get("holding_count", 0),
            latest.get("top_10_concentration", 0),
            status_counts,
            latest_turnover,
            concentration_delta,
        ),
    }


def compare_positions(
    investor: dict[str, Any],
    current: dict[str, dict[str, Any]],
    previous: dict[str, dict[str, Any]],
    current_report_date: str | None,
    previous_report_date: str | None,
) -> list[dict[str, Any]]:
    total_current = sum_number(position["value_usd"] for position in current.values())
    total_previous = sum_number(position["value_usd"] for position in previous.values())
    current_category_totals = totals_by_category(current)
    previous_category_totals = totals_by_category(previous)
    rows: list[dict[str, Any]] = []
    for key in sorted(set(current) | set(previous)):
        current_position = current.get(key)
        previous_position = previous.get(key)
        current_value = safe_number(current_position, "value_usd")
        previous_value = safe_number(previous_position, "value_usd")
        current_shares = safe_number(current_position, "shares")
        previous_shares = safe_number(previous_position, "shares")
        status = classify_change(current_position, previous_position, current_shares, previous_shares)
        display_position = current_position or previous_position or {}
        issuer = display_position.get("issuer")
        category = display_position.get("category", "equity")

        rows.append(
            {
                "investor_slug": investor["slug"],
                "investor": investor["investor"],
                "manager": investor["manager"],
                "position_key": key,
                "issuer": issuer,
                "title_of_class": display_position.get("title_of_class"),
                "cusip": display_position.get("cusip"),
                "put_call": display_position.get("put_call"),
                "category": category,
                "status": status,
                "current_report_date": current_report_date,
                "previous_report_date": previous_report_date,
                "current_value_usd": current_value,
                "previous_value_usd": previous_value,
                "value_delta_usd": current_value - previous_value,
                "current_weight": ratio(current_value, total_current),
                "previous_weight": ratio(previous_value, total_previous),
                "current_category_weight": ratio(current_value, current_category_totals[category]),
                "previous_category_weight": ratio(previous_value, previous_category_totals[category]),
                "current_shares": current_shares,
                "previous_shares": previous_shares,
                "share_delta": current_shares - previous_shares,
                "share_delta_pct": ratio(current_shares - previous_shares, previous_shares),
            }
        )
    return rows


def aggregate_positions(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    positions: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = position_key(row)
        position = positions.setdefault(
            key,
            {
                "position_key": key,
                "issuer": row.get("issuer"),
                "title_of_class": row.get("title_of_class"),
                "cusip": row.get("cusip"),
                "figi": row.get("figi"),
                "put_call": row.get("put_call"),
                "category": holding_category(row),
                "share_type": row.get("share_type"),
                "value_usd": 0.0,
                "value_thousands": 0.0,
                "shares": 0.0,
            },
        )
        position["value_usd"] += row.get("value_usd") or 0
        position["value_thousands"] += row.get("value_thousands") or 0
        position["shares"] += row.get("shares") or 0
    return positions


def totals_by_category(positions: dict[str, dict[str, Any]]) -> dict[str, float]:
    totals = {"equity": 0.0, "option": 0.0}
    for position in positions.values():
        category = position.get("category", "equity")
        totals[category] = totals.get(category, 0.0) + float(position.get("value_usd") or 0)
    return totals


def holding_category(row: dict[str, Any]) -> str:
    title = str(row.get("title_of_class") or "").lower()
    if row.get("put_call") or "option" in title:
        return "option"
    return "equity"


def build_watchlist(
    latest_holdings: list[dict[str, Any]],
    latest_changes: list[dict[str, Any]],
    all_holdings: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    latest_holdings = aggregate_watchlist_holdings(latest_holdings)
    latest_changes = aggregate_watchlist_changes(latest_changes)
    lifecycle_index = build_lifecycle_index(all_holdings or [])

    owners_by_position: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for holding in latest_holdings:
        owners_by_position[holding["position_key"]].append(holding)

    changes_by_position_owner: dict[tuple[str, str], dict[str, Any]] = {}
    changes_by_position: dict[str, list[dict[str, Any]]] = defaultdict(list)
    candidate_keys: set[str] = set()
    for change in latest_changes:
        key = change["position_key"]
        owner_id = change.get("investor_slug") or change.get("investor") or ""
        changes_by_position_owner[(key, owner_id)] = change
        changes_by_position[key].append(change)
        if change["status"] in {"new", "added"} and change["current_value_usd"] > 0:
            candidate_keys.add(key)
        elif change["status"] == "reduced" and (
            change["current_value_usd"] >= 500_000_000 or change["current_weight"] >= 0.1
        ):
            candidate_keys.add(key)

    candidates: list[dict[str, Any]] = []
    for key in candidate_keys:
        changes = changes_by_position[key]
        owner_holdings = sorted(
            owners_by_position.get(key, []),
            key=lambda item: item.get("value_usd") or 0,
            reverse=True,
        )
        owner_details = build_owner_details(owner_holdings, changes_by_position_owner)
        owners = [owner["investor"] for owner in owner_details]
        buyer_names = sorted({change["investor"] for change in changes if change["status"] in {"new", "added"}})
        exemplar = max(owner_holdings or changes, key=lambda item: item.get("current_value_usd") or item.get("value_usd") or 0)
        score = 0.0
        reasons: list[str] = []

        new_buyers = [change for change in changes if change["status"] == "new"]
        adds = [change for change in changes if change["status"] == "added"]
        reducers = [change for change in changes if change["status"] == "reduced"]
        if new_buyers:
            score += 2.0 + min(len(new_buyers) - 1, 3) * 0.5
            reasons.append(f"New position for {join_names(change['investor'] for change in new_buyers)}")
        if adds:
            score += 1.25 + min(len(adds) - 1, 3) * 0.4
            reasons.append(f"Added by {join_names(change['investor'] for change in adds)}")
        if reducers:
            score += 0.75
            reasons.append(f"Reduced by {join_names(change['investor'] for change in reducers)}")
        if len(owners) >= 2:
            score += min(len(owners), 5) * 0.45
            reasons.append(f"Owned by {len(owners)} tracked investors")

        largest_weight = max((owner["current_weight"] for owner in owner_details), default=0.0)
        largest_category_weight = max((owner["current_category_weight"] for owner in owner_details), default=0.0)
        if largest_weight >= 0.1:
            score += 2.0
            reasons.append("Large current weight in at least one portfolio")
        elif largest_weight >= 0.03:
            score += 1.0
            reasons.append("Meaningful current weight in at least one portfolio")
        largest_value = max((owner["current_value_usd"] for owner in owner_details), default=0.0)
        if largest_value >= 500_000_000:
            score += 1.0
            reasons.append("Large disclosed dollar position")

        commentary = build_watchlist_commentary(exemplar, owner_details)
        lifecycle = build_lifecycle_rows(key, owner_details, lifecycle_index)
        candidates.append(
            {
                "position_key": key,
                "issuer": exemplar["issuer"],
                "title_of_class": exemplar["title_of_class"],
                "cusip": exemplar["cusip"],
                "score": round(score, 2),
                "category": exemplar["category"],
                "buyers": buyer_names,
                "owners": owners,
                "owner_details": owner_details,
                "largest_current_value_usd": largest_value,
                "largest_current_weight": largest_weight,
                "largest_current_category_weight": largest_category_weight,
                "reasons": reasons[:4],
                "portfolio_commentary": commentary,
                "research_prompt": commentary,
                "lifecycle": lifecycle,
            }
        )

    return sorted(candidates, key=lambda item: (item["score"], item["largest_current_value_usd"]), reverse=True)[:50]


def aggregate_watchlist_holdings(holdings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for holding in holdings:
        key = watchlist_key(holding)
        owner_id = holding.get("investor_slug") or holding.get("investor") or ""
        position = grouped.setdefault(
            (key, owner_id),
            {
                "position_key": key,
                "issuer": holding.get("issuer"),
                "title_of_class": holding.get("title_of_class"),
                "cusip": holding.get("cusip"),
                "figi": holding.get("figi"),
                "put_call": normalized_put_call(holding),
                "category": holding.get("category") or holding_category(holding),
                "share_type": holding.get("share_type"),
                "value_usd": 0.0,
                "value_thousands": 0.0,
                "shares": 0.0,
                "investor_slug": holding.get("investor_slug"),
                "investor": holding.get("investor"),
                "manager": holding.get("manager"),
                "report_date": holding.get("report_date"),
                "filing_date": holding.get("filing_date"),
                "sec_url": holding.get("sec_url"),
                "weight": 0.0,
                "category_weight": 0.0,
                "category_total_usd": holding.get("category_total_usd"),
                "_display_value": -1.0,
            },
        )
        value = safe_number(holding, "value_usd")
        position["value_usd"] += value
        position["value_thousands"] += safe_number(holding, "value_thousands")
        position["shares"] += safe_number(holding, "shares")
        position["weight"] += safe_number(holding, "weight")
        position["category_weight"] += safe_number(holding, "category_weight")
        if value > position["_display_value"]:
            position["_display_value"] = value
            position["issuer"] = holding.get("issuer")
            position["title_of_class"] = holding.get("title_of_class")
            position["cusip"] = holding.get("cusip")
            position["figi"] = holding.get("figi")
            position["share_type"] = holding.get("share_type")
            position["report_date"] = holding.get("report_date")
            position["filing_date"] = holding.get("filing_date")
            position["sec_url"] = holding.get("sec_url")
    for position in grouped.values():
        position.pop("_display_value", None)
    return list(grouped.values())


def aggregate_watchlist_changes(changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for change in changes:
        key = watchlist_key(change)
        owner_id = change.get("investor_slug") or change.get("investor") or ""
        item = grouped.setdefault(
            (key, owner_id),
            {
                "investor_slug": change.get("investor_slug"),
                "investor": change.get("investor"),
                "manager": change.get("manager"),
                "position_key": key,
                "issuer": change.get("issuer"),
                "title_of_class": change.get("title_of_class"),
                "cusip": change.get("cusip"),
                "put_call": normalized_put_call(change),
                "category": change.get("category") or holding_category(change),
                "status": "held",
                "current_report_date": change.get("current_report_date"),
                "previous_report_date": change.get("previous_report_date"),
                "current_value_usd": 0.0,
                "previous_value_usd": 0.0,
                "value_delta_usd": 0.0,
                "current_weight": 0.0,
                "previous_weight": 0.0,
                "current_category_weight": 0.0,
                "previous_category_weight": 0.0,
                "current_shares": 0.0,
                "previous_shares": 0.0,
                "share_delta": 0.0,
                "share_delta_pct": 0.0,
                "_display_value": -1.0,
            },
        )
        current_value = safe_number(change, "current_value_usd")
        previous_value = safe_number(change, "previous_value_usd")
        item["current_value_usd"] += current_value
        item["previous_value_usd"] += previous_value
        item["current_weight"] += safe_number(change, "current_weight")
        item["previous_weight"] += safe_number(change, "previous_weight")
        item["current_category_weight"] += safe_number(change, "current_category_weight")
        item["previous_category_weight"] += safe_number(change, "previous_category_weight")
        item["current_shares"] += safe_number(change, "current_shares")
        item["previous_shares"] += safe_number(change, "previous_shares")
        display_value = max(current_value, previous_value)
        if display_value > item["_display_value"]:
            item["_display_value"] = display_value
            item["issuer"] = change.get("issuer")
            item["title_of_class"] = change.get("title_of_class")
            item["cusip"] = change.get("cusip")

    for item in grouped.values():
        item["value_delta_usd"] = item["current_value_usd"] - item["previous_value_usd"]
        item["share_delta"] = item["current_shares"] - item["previous_shares"]
        item["share_delta_pct"] = ratio(item["share_delta"], item["previous_shares"])
        current_position = item if item["current_value_usd"] > 0 or item["current_shares"] > 0 else None
        previous_position = item if item["previous_value_usd"] > 0 or item["previous_shares"] > 0 else None
        item["status"] = classify_change(current_position, previous_position, item["current_shares"], item["previous_shares"])
        item.pop("_display_value", None)
    return list(grouped.values())


def build_lifecycle_index(holdings: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    report_dates_by_owner: dict[str, set[str]] = defaultdict(set)
    total_by_owner_report: dict[tuple[str, str], float] = defaultdict(float)
    category_total_by_owner_report: dict[tuple[str, str, str], float] = defaultdict(float)
    positions: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(lambda: {"value_usd": 0.0, "shares": 0.0})
    category_by_key_owner: dict[tuple[str, str], str] = {}

    for row in holdings:
        owner_id = row.get("investor_slug") or row.get("investor") or ""
        report_date = row.get("report_date")
        if not owner_id or not report_date:
            continue
        key = watchlist_key(row)
        category = row.get("category") or holding_category(row)
        value = safe_number(row, "value_usd")
        report_dates_by_owner[owner_id].add(report_date)
        total_by_owner_report[(owner_id, report_date)] += value
        category_total_by_owner_report[(owner_id, report_date, category)] += value
        position = positions[(key, owner_id, report_date)]
        position["value_usd"] += value
        position["shares"] += safe_number(row, "shares")
        category_by_key_owner[(key, owner_id)] = category

    index: dict[tuple[str, str], list[dict[str, Any]]] = {}
    keys_by_owner = {(key, owner_id) for key, owner_id, _ in positions}
    for key, owner_id in keys_by_owner:
        category = category_by_key_owner.get((key, owner_id), "equity")
        points: list[dict[str, Any]] = []
        for report_date in sorted(report_dates_by_owner[owner_id]):
            position = positions.get((key, owner_id, report_date), {})
            value = safe_number(position, "value_usd")
            points.append(
                {
                    "report_date": report_date,
                    "value_usd": value,
                    "shares": safe_number(position, "shares"),
                    "weight": ratio(value, total_by_owner_report[(owner_id, report_date)]),
                    "category_weight": ratio(value, category_total_by_owner_report[(owner_id, report_date, category)]),
                }
            )
        index[(key, owner_id)] = points
    return index


def build_lifecycle_rows(
    key: str,
    owner_details: list[dict[str, Any]],
    lifecycle_index: dict[tuple[str, str], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for owner in owner_details:
        owner_id = owner.get("investor_slug") or owner.get("investor") or ""
        points = lifecycle_index.get((key, owner_id), [])
        if not points:
            continue
        active_points = [point for point in points if point["value_usd"] > 0]
        rows.append(
            {
                "investor": owner["investor"],
                "investor_slug": owner.get("investor_slug"),
                "portfolio_name": owner.get("portfolio_name"),
                "status": owner.get("status") or "held",
                "first_report_date": active_points[0]["report_date"] if active_points else None,
                "latest_report_date": points[-1]["report_date"] if points else None,
                "current_weight": owner.get("current_weight") or 0,
                "peak_weight": max((point["weight"] for point in points), default=0.0),
                "points": points,
            }
        )
    return rows


def build_owner_details(
    owner_holdings: list[dict[str, Any]],
    changes_by_position_owner: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for holding in owner_holdings:
        owner_id = holding.get("investor_slug") or holding.get("investor") or ""
        change = changes_by_position_owner.get((holding["position_key"], owner_id), {})
        details.append(
            {
                "investor": holding["investor"],
                "investor_slug": holding.get("investor_slug"),
                "portfolio_name": holding.get("manager") or holding.get("portfolio_name") or holding["investor"],
                "status": change.get("status") or "held",
                "current_value_usd": safe_number(holding, "value_usd"),
                "current_weight": safe_number(holding, "weight"),
                "current_category_weight": safe_number(holding, "category_weight"),
                "value_delta_usd": safe_number(change, "value_delta_usd"),
                "share_delta_pct": safe_number(change, "share_delta_pct"),
            }
        )
    return details


def build_watchlist_commentary(exemplar: dict[str, Any], owner_details: list[dict[str, Any]]) -> str:
    issuer = exemplar.get("issuer") or "This position"
    side = "options" if exemplar.get("category") == "option" else "equity/non-option"
    if not owner_details:
        return f"{issuer} is a latest-quarter watchlist candidate, but no current owner detail was available in the parsed holdings."

    largest_owner = max(owner_details, key=lambda item: item["current_value_usd"])
    holder_word = "investor" if len(owner_details) == 1 else "investors"
    parts = [
        f"{issuer} appears in the {side} book of {len(owner_details)} tracked {holder_word}. "
        f"The largest disclosed owner here is {largest_owner['investor']} at {money_text(largest_owner['current_value_usd'])}, "
        f"or {percent_text(largest_owner['current_weight'])} of that investor's total 13F book."
    ]

    buyers = sorted(
        [owner for owner in owner_details if owner["status"] in {"new", "added"}],
        key=lambda item: abs(item["value_delta_usd"]),
        reverse=True,
    )
    reducers = sorted(
        [owner for owner in owner_details if owner["status"] == "reduced"],
        key=lambda item: abs(item["value_delta_usd"]),
        reverse=True,
    )
    holders = [owner for owner in owner_details if owner["status"] == "held"]

    if buyers:
        parts.append(f"Latest-quarter buying is led by {join_phrases(describe_owner_action(owner) for owner in buyers[:3])}.")
    if reducers:
        parts.append(f"The signal is mixed because {join_phrases(describe_owner_action(owner) for owner in reducers[:2])}.")
    if not buyers and holders:
        parts.append("Current ownership is mostly held rather than fresh buying, so the signal is more consensus ownership than latest-quarter momentum.")

    if len(owner_details) >= 3:
        parts.append("Because several tracked managers own it, compare whether the thesis is shared or whether one manager is expressing it through a different side of the book.")
    else:
        parts.append("Treat this as a manager-specific lead and compare the position size against that manager's usual concentration before acting on it.")
    return " ".join(parts)


def describe_owner_action(owner: dict[str, Any]) -> str:
    status = owner.get("status") or "held"
    if status == "new":
        action = "opened a new position"
    elif status == "added":
        action = f"added {percent_text(abs(owner.get('share_delta_pct') or 0))} shares"
    elif status == "reduced":
        action = f"reduced {percent_text(abs(owner.get('share_delta_pct') or 0))} shares"
    else:
        action = status
    return (
        f"{owner['investor']} ({action}; {money_text(owner.get('current_value_usd'))} current, "
        f"{percent_text(owner.get('current_weight'))} of total 13F)"
    )


def money_text(value: float | int | None) -> str:
    number = float(value or 0)
    sign = "-" if number < 0 else ""
    absolute = abs(number)
    if absolute >= 1_000_000_000:
        return f"{sign}${absolute / 1_000_000_000:.2f}B"
    if absolute >= 1_000_000:
        return f"{sign}${absolute / 1_000_000:.1f}M"
    if absolute >= 1_000:
        return f"{sign}${absolute / 1_000:.1f}K"
    return f"{sign}${absolute:.0f}"


def percent_text(value: float | int | None) -> str:
    number = float(value or 0) * 100
    if abs(number) >= 10:
        return f"{number:.0f}%"
    return f"{number:.1f}%"


def join_phrases(phrases: Any) -> str:
    items = [str(phrase) for phrase in phrases if phrase]
    if len(items) <= 2:
        return " and ".join(items)
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def watchlist_key(row: dict[str, Any]) -> str:
    identifier = str(row.get("cusip") or "").strip().upper()
    if not identifier:
        identifier = "NO-CUSIP:" + normalize_security_name(row.get("issuer"))
    category = row.get("category") or holding_category(row)
    put_call = normalized_put_call(row) if category == "option" else ""
    return "|".join([identifier, category, put_call])


def normalized_put_call(row: dict[str, Any]) -> str:
    return str(row.get("put_call") or "").strip().title()


def normalize_security_name(value: Any) -> str:
    return " ".join(str(value or "").upper().split())


def position_key(row: dict[str, Any]) -> str:
    return "|".join(
        [
            str(row.get("cusip") or "NO-CUSIP").strip(),
            str(row.get("title_of_class") or "").strip(),
            str(row.get("put_call") or "").strip(),
        ]
    )


def classify_change(
    current_position: dict[str, Any] | None,
    previous_position: dict[str, Any] | None,
    current_shares: float,
    previous_shares: float,
) -> str:
    if current_position and not previous_position:
        return "new"
    if previous_position and not current_position:
        return "exited"
    if previous_shares <= 0:
        return "held"
    pct_change = (current_shares - previous_shares) / previous_shares
    if pct_change >= 0.02:
        return "added"
    if pct_change <= -0.02:
        return "reduced"
    return "held"


def pattern_summary(
    holding_count: int,
    concentration: float,
    status_counts: dict[str, int],
    turnover: float,
    concentration_delta: float,
) -> list[str]:
    summary: list[str] = []
    if holding_count >= 500:
        summary.append("Very broad disclosed book; focus on high-weight changes rather than every line item.")
    elif concentration >= 0.75:
        summary.append("Highly concentrated long book; top holdings dominate the signal.")
    elif concentration >= 0.5:
        summary.append("Moderately concentrated portfolio with meaningful top-10 signal.")
    else:
        summary.append("Diversified disclosed book; use position-size filters to separate signal from noise.")

    if status_counts.get("new", 0) + status_counts.get("exited", 0) >= max(8, holding_count * 0.25):
        summary.append("High position churn in the latest quarter.")
    elif turnover >= 0.2:
        summary.append("Material quarter-over-quarter reshaping by disclosed value.")
    else:
        summary.append("Latest quarter looks more like incremental adjustment than wholesale repositioning.")

    if concentration_delta >= 0.05:
        summary.append("Top-10 concentration rose versus the earliest loaded quarter.")
    elif concentration_delta <= -0.05:
        summary.append("Top-10 concentration fell versus the earliest loaded quarter.")
    return summary



def turnover_proxy(changes: list[dict[str, Any]], current_total: float | None, previous_total: float | None) -> float:
    denominator = average(value for value in [current_total or 0, previous_total or 0] if value)
    changed_value = sum(
        abs(change["value_delta_usd"])
        for change in changes
        if change["status"] in {"new", "exited", "added", "reduced"}
    )
    return ratio(changed_value, denominator)


def count_statuses(changes: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for change in changes:
        counts[change["status"]] += 1
    return dict(counts)


def change_sort_key(change: dict[str, Any]) -> tuple[int, float]:
    priority = {"new": 0, "exited": 1, "added": 2, "reduced": 3, "held": 4}
    return (priority.get(change["status"], 9), -abs(change["value_delta_usd"]))


def group_by(rows: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row.get(key)].append(row)
    return grouped


def first_value(rows: list[dict[str, Any]], key: str) -> Any:
    for row in rows:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def safe_number(row: dict[str, Any] | None, key: str) -> float:
    if not row:
        return 0.0
    value = row.get(key)
    return float(value or 0)


def sum_number(values: Any) -> float:
    return float(sum(value or 0 for value in values))


def ratio(numerator: float | int | None, denominator: float | int | None) -> float:
    if not denominator:
        return 0.0
    return float(numerator or 0) / float(denominator)


def average(values: Any) -> float:
    items = [float(value) for value in values if value is not None]
    if not items:
        return 0.0
    return sum(items) / len(items)


def join_names(names: Any) -> str:
    items = sorted(set(str(name) for name in names))
    if len(items) <= 2:
        return " and ".join(items)
    return ", ".join(items[:-1]) + f", and {items[-1]}"
