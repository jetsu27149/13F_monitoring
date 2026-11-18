#!/usr/bin/env python3
from __future__ import annotations

import argparse
import errno
import json
import os
import re
import subprocess
import sys
import threading
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

from thirteenf.quarters import build_quarter, load_report, report_files
from thirteenf.refresh import load_env_file, run_incremental_refresh, user_agent_looks_unset
from thirteenf.sec_client import SecClient, SecClientError


QUARTER_CACHE: dict[str, dict[str, Any]] = {}

# Guards REFRESH_STATE. A refresh rewrites dashboard.json in place, so only one
# may run at a time; a second click must join the running job, not start another.
REFRESH_LOCK = threading.Lock()
REFRESH_STATE: dict[str, Any] = {
    "state": "idle",  # idle | running | done | error
    "progress": 0.0,
    "message": "",
    "started_at": None,
    "finished_at": None,
    "summary": None,
    "error": None,
}


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
            if path == "/api/refresh-filings":
                self.send_json(handle_refresh_filings(payload))
                return
            if path == "/api/refresh-status":
                self.send_json(handle_refresh_status())
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


def refresh_snapshot() -> dict[str, Any]:
    """A copy of the current refresh job state, safe to serialise."""
    with REFRESH_LOCK:
        return dict(REFRESH_STATE)


def handle_refresh_status() -> dict[str, Any]:
    return refresh_snapshot()


def handle_refresh_filings(payload: dict[str, Any]) -> dict[str, Any]:
    """Start a background download of any filings SEC has that we do not.

    Returns immediately. The browser polls /api/refresh-status for progress,
    which keeps a slow multi-investor pull from tripping request timeouts.
    """
    investor_slugs = requested_investor_slugs(payload)
    investors = load_json(ROOT / "investors.json")
    if investor_slugs is not None:
        selected = set(investor_slugs)
        investors = [investor for investor in investors if investor.get("slug") in selected]
    if not investors:
        return {"error": "No matching investor found to refresh.", "started": False}

    user_agent = os.environ.get("SEC_USER_AGENT", DEFAULT_USER_AGENT)
    quarters = max(1, min(int(payload.get("quarters") or 4), 40))

    with REFRESH_LOCK:
        if REFRESH_STATE["state"] == "running":
            return {"started": False, "already_running": True, **REFRESH_STATE}
        REFRESH_STATE.update(
            {
                "state": "running",
                "progress": 0.0,
                "message": f"Checking SEC for {len(investors)} investor(s)...",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "finished_at": None,
                "summary": None,
                "error": None,
            }
        )

    thread = threading.Thread(
        target=run_refresh_job,
        args=(investors, user_agent, quarters),
        name="13f-refresh",
        daemon=True,
    )
    thread.start()
    return {
        "started": True,
        "investors": len(investors),
        "user_agent_unset": user_agent_looks_unset(user_agent),
        **refresh_snapshot(),
    }


def run_refresh_job(investors: list[dict[str, Any]], user_agent: str, quarters: int) -> None:
    """Background worker: download new filings and rebuild the dashboard."""

    def progress(fraction: float, message: str) -> None:
        with REFRESH_LOCK:
            REFRESH_STATE["progress"] = max(0.0, min(1.0, float(fraction)))
            REFRESH_STATE["message"] = message

    try:
        summary = run_incremental_refresh(
            root=ROOT,
            investors=investors,
            user_agent=user_agent,
            quarters=quarters,
            progress=progress,
        )
    except Exception as exc:  # noqa: BLE001 - surface any failure to the browser
        with REFRESH_LOCK:
            REFRESH_STATE.update(
                {
                    "state": "error",
                    "error": public_error_message(exc),
                    "message": "Refresh failed.",
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        return

    # dashboard.json was rewritten, so any per-quarter slices we cached are stale.
    if summary.get("rebuilt"):
        QUARTER_CACHE.clear()

    with REFRESH_LOCK:
        REFRESH_STATE.update(
            {
                "state": "done",
                "progress": 1.0,
                "message": summary.get("message") or REFRESH_STATE.get("message") or "Refresh complete.",
                "summary": summary,
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }
        )


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
        "user_agent_unset": user_agent_looks_unset(os.environ.get("SEC_USER_AGENT", DEFAULT_USER_AGENT)),
        "results": results,
    }


def handle_quarter(payload: dict[str, Any]) -> dict[str, Any]:
    report_date = str(payload.get("report_date") or "").strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", report_date):
        return {"error": "Choose a valid report date."}
    if report_date not in QUARTER_CACHE:
        QUARTER_CACHE[report_date] = build_quarter(ROOT, report_date)
    return QUARTER_CACHE[report_date]


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
    """One entry per quarter for a manager, newest first, amendments applied."""
    reports = []
    for report_date, paths in report_files(ROOT).get(slug, {}).items():
        rows = load_report(paths)
        if not rows:
            continue
        reports.append(
            {
                "report_date": report_date,
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
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), DashboardHandler)
    except OSError as exc:
        if exc.errno != errno.EADDRINUSE:
            raise
        # An earlier server is still holding the port. Python does not reload
        # code, so that process is serving whatever revision it started with --
        # which shows up in the browser as endpoints 404ing for no clear reason.
        print(
            f"\n  Port {args.port} is already in use, most likely by an earlier dashboard server.\n"
            "  That process is still serving the code it started with, so new endpoints\n"
            "  will 404 until you replace it. Stop it and start again:\n\n"
            f"    lsof -ti tcp:{args.port} | xargs kill\n"
            f"    python3 scripts/dashboard_server.py --port {args.port}\n\n"
            f"  Or leave it running and use another port: --port {args.port + 1}\n",
            file=sys.stderr,
        )
        return 1
    url = f"http://127.0.0.1:{args.port}/dashboard/"
    print(f"Serving 13F dashboard at {url}")
    print("Optional env vars: OPENAI_API_KEY, OPENAI_MODEL, FMP_API_KEY, FINNHUB_API_KEY")
    if user_agent_looks_unset(os.environ.get("SEC_USER_AGENT", DEFAULT_USER_AGENT)):
        print(
            "\n  WARNING: SEC_USER_AGENT is not set, so requests go out as\n"
            f'    "{DEFAULT_USER_AGENT}"\n'
            "  SEC rejects clients that do not give a working contact address, so filing\n"
            "  checks and downloads will fail. Add this to your .env and restart:\n"
            '    SEC_USER_AGENT="13F Monitoring local dashboard your-real-email@example.com"\n'
        )
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
