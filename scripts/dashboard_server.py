#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DEFAULT_USER_AGENT = "13F Monitoring local dashboard contact@example.com"
sys.path.insert(0, str(ROOT / "src"))

from thirteenf.analytics import (
    aggregate_positions as analytics_aggregate_positions,
    build_watchlist as analytics_build_watchlist,
    change_sort_key as analytics_change_sort_key,
    compare_positions as analytics_compare_positions,
    count_statuses as analytics_count_statuses,
    pattern_summary as analytics_pattern_summary,
    ratio as analytics_ratio,
    summarize_report as analytics_summarize_report,
    totals_by_category as analytics_totals_by_category,
    turnover_proxy as analytics_turnover_proxy,
)
from thirteenf.sec_client import SecClient, SecClientError


QUARTER_CACHE: dict[str, dict[str, Any]] = {}


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


class DashboardHandler(SimpleHTTPRequestHandler):
    server_version = "ThirteenFDashboard/0.1"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            payload = self.read_json_body()
            if path == "/api/ask":
                self.send_json(handle_ask(payload))
                return
            if path == "/api/ticker":
                self.send_json(handle_ticker(payload))
                return
            if path == "/api/earnings":
                self.send_json(handle_earnings(payload))
                return
            if path == "/api/check-filings":
                self.send_json(handle_check_filings(payload))
                return
            if path == "/api/quarter":
                self.send_json(handle_quarter(payload))
                return
            self.send_error(HTTPStatus.NOT_FOUND, "Unknown API endpoint")
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw or "{}")

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def handle_ask(payload: dict[str, Any]) -> dict[str, Any]:
    question = str(payload.get("question") or "").strip()
    if not question:
        return {"error": "Ask a question about the filings first."}

    investor_slugs = requested_investor_slugs(payload)
    quarters = clamp_int(payload.get("quarters"), 1, 20, 20)
    category = str(payload.get("category") or "all")
    context = build_filing_context(investor_slugs, quarters, category)

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {
            "answer": (
                "OPENAI_API_KEY is not set on the local server, so I cannot call an LLM yet.\n\n"
                "Here is the filing context that would be sent to the model:\n\n"
                f"{context}"
            )
        }

    instructions = (
        "You are a buy-side research assistant analyzing SEC Form 13F filings. "
        "Use only the provided filing context. Be explicit about report dates, separate equity/non-option rows from options, "
        "and explain limitations. Do not provide financial advice or claim the filing shows shorts, cash, or full macro exposure."
    )
    prompt = f"Question: {question}\n\nLocal SEC filing context:\n{context}"
    answer = call_openai(prompt, instructions)
    return {"answer": answer}


def handle_ticker(payload: dict[str, Any]) -> dict[str, Any]:
    symbol = normalize_symbol(str(payload.get("symbol") or ""))
    if not symbol:
        return {"error": "Enter a stock ticker."}

    fmp_key = os.environ.get("FMP_API_KEY")
    if fmp_key:
        try:
            return {"summary": fmp_ticker_summary(symbol, fmp_key)}
        except RuntimeError as exc:
            return {"error": public_error_message(exc)}

    finnhub_key = os.environ.get("FINNHUB_API_KEY")
    if finnhub_key:
        return {"summary": finnhub_ticker_summary(symbol, finnhub_key)}

    return {
        "error": (
            "No market-data API key is configured. Set FMP_API_KEY for Financial Modeling Prep "
            "or FINNHUB_API_KEY for Finnhub before starting the local server."
        )
    }


def handle_earnings(payload: dict[str, Any]) -> dict[str, Any]:
    symbol = normalize_symbol(str(payload.get("symbol") or ""))
    if not symbol:
        return {"error": "Enter a stock ticker."}

    fmp_key = os.environ.get("FMP_API_KEY")
    if not fmp_key:
        return {
            "error": (
                "FMP_API_KEY is not set on the local server. Restart the dashboard with "
                "FMP_API_KEY exported to load past earnings report data."
            )
        }

    try:
        return {"summary": fmp_earnings_summary(symbol, fmp_key)}
    except RuntimeError as exc:
        return {"error": public_error_message(exc)}


def handle_check_filings(payload: dict[str, Any]) -> dict[str, Any]:
    investor_slugs = requested_investor_slugs(payload)
    investors = load_json(ROOT / "investors.json")
    if investor_slugs is not None:
        selected = set(investor_slugs)
        investors = [investor for investor in investors if investor.get("slug") in selected]
    if not investors:
        return {"error": "No matching investor found for the filing check."}

    dashboard = load_json(DATA_DIR / "processed" / "dashboard.json")
    local_by_slug = {item.get("slug"): item for item in dashboard.get("investors", [])}
    client = SecClient(
        cache_dir=DATA_DIR / "cache",
        user_agent=os.environ.get("SEC_USER_AGENT", DEFAULT_USER_AGENT),
    )

    results: list[dict[str, Any]] = []
    for investor in investors:
        local = local_by_slug.get(investor.get("slug"), {})
        try:
            filings = client.recent_13f_filings(investor["cik"], limit=1, refresh=True)
            if not filings:
                results.append(
                    {
                        "investor": investor.get("investor"),
                        "investor_slug": investor.get("slug"),
                        "error": "No recent 13F filings found at SEC.",
                    }
                )
                continue

            latest = filings[0]
            local_report_date = local.get("latest_report_date")
            local_filing_date = local.get("latest_filing_date")
            new_available = is_new_sec_filing(
                latest.report_date,
                latest.filing_date,
                local_report_date,
                local_filing_date,
            )
            results.append(
                {
                    "investor": investor.get("investor"),
                    "investor_slug": investor.get("slug"),
                    "manager": investor.get("manager"),
                    "new_available": new_available,
                    "sec_report_date": latest.report_date,
                    "sec_filing_date": latest.filing_date,
                    "sec_form": latest.form,
                    "sec_accession_number": latest.accession_number,
                    "sec_url": latest.sec_url,
                    "local_report_date": local_report_date,
                    "local_filing_date": local_filing_date,
                    "local_value_usd": local.get("total_value_usd"),
                }
            )
        except (SecClientError, OSError, KeyError, ValueError) as exc:
            results.append(
                {
                    "investor": investor.get("investor"),
                    "investor_slug": investor.get("slug"),
                    "error": str(exc),
                    "local_report_date": local.get("latest_report_date"),
                    "local_filing_date": local.get("latest_filing_date"),
                }
            )

    new_count = sum(1 for item in results if item.get("new_available"))
    error_count = sum(1 for item in results if item.get("error"))
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "scope": investor_slugs or "all",
        "checked_count": len(results),
        "new_count": new_count,
        "error_count": error_count,
        "results": results,
    }


def handle_quarter(payload: dict[str, Any]) -> dict[str, Any]:
    report_date = str(payload.get("report_date") or "").strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", report_date):
        return {"error": "Choose a valid report date."}
    if report_date not in QUARTER_CACHE:
        QUARTER_CACHE[report_date] = build_quarter_dashboard(report_date)
    return QUARTER_CACHE[report_date]


def build_quarter_dashboard(report_date: str) -> dict[str, Any]:
    investors = load_json(ROOT / "investors.json")
    base_dashboard = load_json(DATA_DIR / "processed" / "dashboard.json")
    base_by_slug = {item.get("slug"): item for item in base_dashboard.get("investors", [])}
    investor_summaries: list[dict[str, Any]] = []
    selected_holdings: list[dict[str, Any]] = []
    selected_changes: list[dict[str, Any]] = []
    lifecycle_rows: list[dict[str, Any]] = []

    for investor in investors:
        reports = load_raw_reports(investor["slug"])
        lifecycle_rows.extend(row for report in reports for row in report["rows"] if (report.get("report_date") or "") <= report_date)
        current_index = next((index for index, report in enumerate(reports) if report.get("report_date") == report_date), None)
        if current_index is None:
            continue

        current_report = reports[current_index]
        previous_report = reports[current_index + 1] if current_index + 1 < len(reports) else None
        current_rows = current_report["rows"]
        previous_rows = previous_report["rows"] if previous_report else []

        current_positions = analytics_aggregate_positions(current_rows)
        previous_positions = analytics_aggregate_positions(previous_rows)
        current_total = sum_number(position["value_usd"] for position in current_positions.values())
        current_category_totals = analytics_totals_by_category(current_positions)

        for position in sorted(current_positions.values(), key=lambda item: item["value_usd"], reverse=True):
            category_total = current_category_totals[position["category"]]
            selected_holdings.append(
                {
                    **position,
                    "investor_slug": investor["slug"],
                    "investor": investor["investor"],
                    "manager": investor["manager"],
                    "report_date": report_date,
                    "filing_date": current_report.get("filing_date"),
                    "sec_url": current_report.get("sec_url"),
                    "weight": analytics_ratio(position["value_usd"], current_total),
                    "category_weight": analytics_ratio(position["value_usd"], category_total),
                    "category_total_usd": category_total,
                }
            )

        changes = analytics_compare_positions(
            investor,
            current_positions,
            previous_positions,
            report_date,
            previous_report.get("report_date") if previous_report else None,
        )
        selected_changes.extend(changes)
        investor_summaries.append(
            quarter_investor_summary(
                investor,
                base_by_slug.get(investor["slug"], {}),
                current_rows,
                previous_rows,
                current_report,
                previous_report,
                changes,
            )
        )

    watchlist = analytics_build_watchlist(selected_holdings, selected_changes, lifecycle_rows)
    return {
        "metadata": {
            **base_dashboard.get("metadata", {}),
            "selected_report_date": report_date,
            "selected_holding_rows": len(selected_holdings),
            "selected_change_rows": len(selected_changes),
            "selected_investor_count": len(investor_summaries),
        },
        "investors": sorted(investor_summaries, key=lambda item: item["investor"]),
        "holdings": sorted(selected_holdings, key=lambda item: item["weight"], reverse=True),
        "changes": sorted(selected_changes, key=analytics_change_sort_key),
        "watchlist": watchlist,
    }


def quarter_investor_summary(
    investor: dict[str, Any],
    base: dict[str, Any],
    current_rows: list[dict[str, Any]],
    previous_rows: list[dict[str, Any]],
    current_report: dict[str, Any],
    previous_report: dict[str, Any] | None,
    changes: list[dict[str, Any]],
) -> dict[str, Any]:
    report = analytics_summarize_report(investor, current_report["report_date"], current_rows)
    previous_summary = (
        analytics_summarize_report(investor, previous_report["report_date"], previous_rows)
        if previous_report
        else {}
    )
    status_counts = analytics_count_statuses(changes)
    turnover = analytics_turnover_proxy(
        changes,
        report.get("total_value_usd"),
        previous_summary.get("total_value_usd"),
    )
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
        "pattern_summary": analytics_pattern_summary(
            report.get("holding_count", 0),
            report.get("top_10_concentration", 0),
            status_counts,
            turnover,
            concentration_delta,
        ),
    }


def requested_investor_slugs(payload: dict[str, Any]) -> list[str] | None:
    values = payload.get("investor_slugs")
    if isinstance(values, list):
        slugs = [str(value).strip() for value in values if str(value).strip() and str(value).strip() != "all"]
        return slugs or None

    slug = str(payload.get("investor_slug") or "all").strip()
    if slug and slug != "all":
        return [slug]
    return None


def is_new_sec_filing(
    sec_report_date: str | None,
    sec_filing_date: str | None,
    local_report_date: str | None,
    local_filing_date: str | None,
) -> bool:
    if not local_report_date:
        return True
    if (sec_report_date or "") > local_report_date:
        return True
    if sec_report_date == local_report_date and (sec_filing_date or "") > (local_filing_date or ""):
        return True
    return False


def call_openai(prompt: str, instructions: str) -> str:
    model = os.environ.get("OPENAI_MODEL", "gpt-5.2")
    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={
            "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "instructions": instructions,
            "input": prompt,
            "max_output_tokens": 1200,
        },
        timeout=60,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"OpenAI API error {response.status_code}: {response.text[:500]}")
    data = response.json()
    if data.get("output_text"):
        return data["output_text"]
    return extract_response_text(data) or "The model returned no text."


def extract_response_text(data: dict[str, Any]) -> str:
    chunks: list[str] = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                chunks.append(content["text"])
    return "\n".join(chunks)


def build_filing_context(investor_slugs: list[str] | None, quarters: int, category: str) -> str:
    dashboard = load_json(DATA_DIR / "processed" / "dashboard.json")
    investor_map = {item["slug"]: item for item in dashboard.get("investors", [])}
    slugs = list(investor_map) if investor_slugs is None else investor_slugs
    sections: list[str] = []

    for slug in slugs:
        investor = investor_map.get(slug)
        if not investor:
            continue
        reports = load_raw_reports(slug)[:quarters]
        sections.append(f"## {investor['investor']} / {investor['manager']}")
        sections.append(
            "Style seed: "
            f"{investor.get('style', 'n/a')}. Latest report: {investor.get('latest_report_date')} filed {investor.get('latest_filing_date')}."
        )
        sections.append(f"SEC profile: {investor.get('sec_company_url')}")

        row_limit = 5 if quarters > 8 else 10
        for report in reports:
            rows = filter_category(report["rows"], category)
            totals = category_totals(report["rows"])
            report_total = sum_number(row.get("value_usd") for row in rows)
            sections.append(
                f"\nReport {report['report_date']} filed {report['filing_date']} | "
                f"selected value {money(report_total)} | rows {len(rows)} | "
                f"equity {money(totals['equity'])} | options {money(totals['option'])} | {report['sec_url']}"
            )
            for row in top_rows(rows, row_limit):
                denominator = report_total or 1
                sections.append(
                    f"- {row.get('issuer')} | {row.get('title_of_class')} {row.get('put_call') or ''} | "
                    f"CUSIP {row.get('cusip')} | value {money(row.get('value_usd'))} | "
                    f"weight {percent((row.get('value_usd') or 0) / denominator)} | shares {number(row.get('shares'))}"
                )

        if len(reports) >= 2:
            sections.append("\nLargest latest-quarter changes vs prior loaded quarter:")
            latest_positions = aggregate_positions(filter_category(reports[0]["rows"], category))
            prior_positions = aggregate_positions(filter_category(reports[1]["rows"], category))
            for change in compare_reports(latest_positions, prior_positions)[:15]:
                sections.append(
                    f"- {change['status']}: {change['issuer']} | {money(change['current_value'])} now | "
                    f"delta {money(change['delta_value'])} | share change {percent(change['share_delta_pct'])}"
                )

    if not sections:
        return "No local filing context found. Run scripts/refresh_data.py --quarters 20 first."
    return "\n".join(sections)[:36000]


def load_raw_reports(slug: str) -> list[dict[str, Any]]:
    report_dir = DATA_DIR / "raw" / slug
    reports = []
    for path in sorted(report_dir.glob("*.json"), reverse=True):
        rows = load_json(path)
        if not rows:
            continue
        reports.append(
            {
                "report_date": rows[0].get("report_date"),
                "filing_date": rows[0].get("filing_date"),
                "sec_url": rows[0].get("sec_url"),
                "rows": rows,
            }
        )
    return sorted(reports, key=lambda item: item["report_date"] or "", reverse=True)


def filter_category(rows: list[dict[str, Any]], category: str) -> list[dict[str, Any]]:
    if category not in {"equity", "option"}:
        return rows
    return [row for row in rows if holding_category(row) == category]


def holding_category(row: dict[str, Any]) -> str:
    title = str(row.get("title_of_class") or "").lower()
    return "option" if row.get("put_call") or "option" in title else "equity"


def category_totals(rows: list[dict[str, Any]]) -> dict[str, float]:
    totals = {"equity": 0.0, "option": 0.0}
    for row in rows:
        totals[holding_category(row)] += float(row.get("value_usd") or 0)
    return totals


def top_rows(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda item: float(item.get("value_usd") or 0), reverse=True)[:limit]


def aggregate_positions(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    positions: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = "|".join([str(row.get("cusip") or ""), str(row.get("title_of_class") or ""), str(row.get("put_call") or "")])
        position = positions.setdefault(
            key,
            {
                "issuer": row.get("issuer"),
                "value_usd": 0.0,
                "shares": 0.0,
            },
        )
        position["value_usd"] += float(row.get("value_usd") or 0)
        position["shares"] += float(row.get("shares") or 0)
    return positions


def compare_reports(current: dict[str, dict[str, Any]], prior: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    changes = []
    for key in set(current) | set(prior):
        now = current.get(key)
        before = prior.get(key)
        now_value = float((now or {}).get("value_usd") or 0)
        before_value = float((before or {}).get("value_usd") or 0)
        now_shares = float((now or {}).get("shares") or 0)
        before_shares = float((before or {}).get("shares") or 0)
        status = "held"
        if now and not before:
            status = "new"
        elif before and not now:
            status = "exited"
        elif before_shares:
            pct = (now_shares - before_shares) / before_shares
            if pct >= 0.02:
                status = "added"
            elif pct <= -0.02:
                status = "reduced"
        changes.append(
            {
                "issuer": (now or before or {}).get("issuer"),
                "status": status,
                "current_value": now_value,
                "delta_value": now_value - before_value,
                "share_delta_pct": (now_shares - before_shares) / before_shares if before_shares else 0,
            }
        )
    return sorted(changes, key=lambda item: abs(item["delta_value"]), reverse=True)


def fmp_ticker_summary(symbol: str, api_key: str) -> str:
    base = "https://financialmodelingprep.com/stable"
    consensus = request_json(f"{base}/price-target-consensus", {"symbol": symbol, "apikey": api_key})
    rating = request_json(f"{base}/ratings-snapshot", {"symbol": symbol, "apikey": api_key})
    return format_fmp_summary(symbol, consensus, rating)


def fmp_earnings_summary(symbol: str, api_key: str) -> str:
    base = "https://financialmodelingprep.com/stable"
    earnings = request_json(f"{base}/earnings", {"symbol": symbol, "apikey": api_key})
    rows = normalize_earnings_rows(earnings)
    if not rows:
        calendar = request_json(f"{base}/earnings-calendar", {"symbol": symbol, "apikey": api_key})
        rows = normalize_earnings_rows(calendar)
    return format_fmp_earnings_summary(symbol, rows)


def finnhub_ticker_summary(symbol: str, api_key: str) -> str:
    base = "https://finnhub.io/api/v1"
    target = request_json(f"{base}/stock/price-target", {"symbol": symbol, "token": api_key})
    recommendations = request_json(f"{base}/stock/recommendation", {"symbol": symbol, "token": api_key})
    return format_finnhub_summary(symbol, target, recommendations)


def request_json(url: str, params: dict[str, Any]) -> Any:
    response = requests.get(url, params=params, timeout=30)
    if response.status_code >= 400:
        raise RuntimeError(f"Market data request failed {response.status_code}: {response.text[:300]}")
    return response.json()


def public_error_message(error: Exception) -> str:
    message = str(error)
    for env_name in ("OPENAI_API_KEY", "FMP_API_KEY", "FINNHUB_API_KEY"):
        value = os.environ.get(env_name)
        if value:
            message = message.replace(value, "<REDACTED>")
    return message


def format_fmp_summary(symbol: str, consensus: Any, rating: Any) -> str:
    consensus_row = first_row(consensus)
    rating_row = first_row(rating)
    lines = [f"{symbol} analyst snapshot (Financial Modeling Prep)"]
    if rating_row:
        lines.append(f"Rating: {pick(rating_row, 'rating', 'overallRating', 'recommendation', default='n/a')}")
        score = pick(rating_row, "ratingScore", "overallScore", "score", default=None)
        if score is not None:
            lines.append(f"Rating score: {score}")
    if consensus_row:
        lines.append(f"Target consensus: {money(pick_number(consensus_row, 'targetConsensus', 'targetMedian', 'consensus'))}")
        lines.append(f"Target high: {money(pick_number(consensus_row, 'targetHigh', 'high'))}")
        lines.append(f"Target low: {money(pick_number(consensus_row, 'targetLow', 'low'))}")
    if len(lines) == 1:
        lines.append("No rating or target-price data returned by the provider.")
    return "\n".join(lines)


def normalize_earnings_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        rows = [row for row in value if isinstance(row, dict)]
    elif isinstance(value, dict):
        nested = value.get("earnings") or value.get("historical") or value.get("data")
        if isinstance(nested, list):
            rows = [row for row in nested if isinstance(row, dict)]
        else:
            rows = [value]
    else:
        rows = []
    return sorted(rows, key=earnings_row_date, reverse=True)


def earnings_row_date(row: dict[str, Any]) -> str:
    return str(
        pick(
            row,
            "date",
            "fiscalDateEnding",
            "reportedDate",
            "reportDate",
            "updatedFromDate",
            default="",
        )
    )


def format_fmp_earnings_summary(symbol: str, rows: list[dict[str, Any]]) -> str:
    lines = [f"{symbol} past earnings reports (Financial Modeling Prep)"]
    if not rows:
        lines.append("No earnings report rows returned by FMP for this ticker.")
        return "\n".join(lines)

    for row in rows[:6]:
        date = pick(row, "date", "reportedDate", "reportDate", "fiscalDateEnding", default="n/a")
        period = pick(row, "period", "fiscalPeriod", "quarter", default="")
        timing = pick(row, "time", "timeOfDay", default="")
        eps_actual = pick_number(row, "epsActual", "eps", "actualEps", "reportedEPS")
        eps_estimate = pick_number(row, "epsEstimated", "epsEstimate", "estimatedEPS", "estimatedEps")
        revenue_actual = pick_number(row, "revenueActual", "revenue", "actualRevenue")
        revenue_estimate = pick_number(row, "revenueEstimated", "revenueEstimate", "estimatedRevenue")
        surprise = pick_number(row, "epsSurprise", "surprise", "surprisePercent")

        header_parts = [str(date)]
        if period:
            header_parts.append(str(period))
        if timing:
            header_parts.append(str(timing).upper())
        lines.append(
            f"- {' | '.join(header_parts)}: EPS {decimal_or_na(eps_actual)} vs est {decimal_or_na(eps_estimate)}; "
            f"revenue {money_or_na(revenue_actual)} vs est {money_or_na(revenue_estimate)}"
            + (f"; surprise {decimal_or_na(surprise)}" if surprise is not None else "")
        )
    lines.append("Use these as event dates/context, not as a recommendation.")
    return "\n".join(lines)


def format_finnhub_summary(symbol: str, target: Any, recommendations: Any) -> str:
    latest = first_row(recommendations)
    lines = [f"{symbol} analyst snapshot (Finnhub)"]
    if latest:
        period = latest.get("period", "latest")
        lines.append(
            f"Recommendation trend ({period}): strong buy {latest.get('strongBuy', 0)}, "
            f"buy {latest.get('buy', 0)}, hold {latest.get('hold', 0)}, sell {latest.get('sell', 0)}, "
            f"strong sell {latest.get('strongSell', 0)}"
        )
    if isinstance(target, dict) and target:
        lines.append(f"Target mean: {money(target.get('targetMean'))}")
        lines.append(f"Target high: {money(target.get('targetHigh'))}")
        lines.append(f"Target low: {money(target.get('targetLow'))}")
        lines.append(f"Target median: {money(target.get('targetMedian'))}")
        if target.get("lastUpdated"):
            lines.append(f"Last updated: {target.get('lastUpdated')}")
    if len(lines) == 1:
        lines.append("No rating or target-price data returned by the provider.")
    return "\n".join(lines)


def first_row(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        return value[0] if value else {}
    if isinstance(value, dict):
        return value
    return {}


def pick(row: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if row.get(key) not in (None, ""):
            return row[key]
    return default


def pick_number(row: dict[str, Any], *keys: str) -> float | None:
    value = pick(row, *keys, default=None)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def money_or_na(value: Any) -> str:
    if value in (None, ""):
        return "n/a"
    return money(value)


def decimal_or_na(value: Any) -> str:
    if value in (None, ""):
        return "n/a"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "n/a"


def normalize_symbol(symbol: str) -> str:
    match = re.match(r"^[A-Z.\-]{1,12}$", symbol.strip().upper())
    return match.group(0) if match else ""


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sum_number(values: Any) -> float:
    return float(sum(value or 0 for value in values))


def clamp_int(value: Any, low: int, high: int, default: int) -> int:
    try:
        return min(high, max(low, int(value)))
    except (TypeError, ValueError):
        return default


def money(value: Any) -> str:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return "n/a"
    sign = "-" if number < 0 else ""
    number = abs(number)
    if number >= 1_000_000_000:
        return f"{sign}${number / 1_000_000_000:.2f}B"
    if number >= 1_000_000:
        return f"{sign}${number / 1_000_000:.1f}M"
    if number >= 1_000:
        return f"{sign}${number / 1_000:.1f}K"
    return f"{sign}${number:.2f}"


def number(value: Any) -> str:
    try:
        return f"{float(value or 0):,.0f}"
    except (TypeError, ValueError):
        return "0"


def percent(value: Any) -> str:
    try:
        return f"{float(value or 0) * 100:.1f}%"
    except (TypeError, ValueError):
        return "0.0%"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local 13F dashboard with API endpoints.")
    parser.add_argument("--port", default=8013, type=int)
    parser.add_argument("--no-open", action="store_true", help="Start the server without opening Google Chrome.")
    args = parser.parse_args()

    os.chdir(ROOT)
    load_env_file(ROOT / ".env")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), DashboardHandler)
    url = f"http://127.0.0.1:{args.port}/dashboard/"
    print(f"Serving 13F dashboard at {url}")
    print("Optional env vars: OPENAI_API_KEY, OPENAI_MODEL, FMP_API_KEY, FINNHUB_API_KEY")
    if not args.no_open:
        open_error = open_in_chrome(url)
        if open_error:
            print(open_error)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    return 0


def open_in_chrome(url: str) -> str | None:
    if sys.platform != "darwin":
        return f"Open this URL in Google Chrome: {url}"
    try:
        subprocess.Popen(
            ["open", "-na", "Google Chrome", "--args", "--new-window", url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        return f"Could not open Google Chrome automatically: {exc}. Open {url} manually."
    return None


if __name__ == "__main__":
    raise SystemExit(main())
