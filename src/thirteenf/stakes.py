"""Recent stake disclosures by tracked managers: Schedule 13D, 13G and Form 4.

A 13F shows positions up to 45 days after quarter-end. These filings are much
faster: a 13D is due within days of crossing 5% ownership with intent to
influence, a 13G covers passive stakes above 5%, and a Form 4 reports trades by
10%-plus owners within two business days. The submissions index fetched for
the 13F refresh already lists them; this module opens each new one and pulls
out the issuer, the stake and the trades.

Tag names follow EDGAR's structured Schedule 13D/13G XML (in use since
December 2024) and the Form 4 ownershipDocument schema.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from xml.etree import ElementTree as ET

from thirteenf.sec_client import SecClient, SecClientError

ProgressFn = Callable[[float, str], None]

STAKE_FORMS = {
    "SCHEDULE 13D": "13D", "SCHEDULE 13D/A": "13D",
    "SCHEDULE 13G": "13G", "SCHEDULE 13G/A": "13G",
    "SC 13D": "13D", "SC 13D/A": "13D", "SC 13G": "13G", "SC 13G/A": "13G",
    "4": "4", "4/A": "4",
}

# Words that say nothing about which firm a filer is, dropped when deriving
# the brand used to spot a manager's own vehicles among issuers.
GENERIC_WORDS = {
    "LLC", "LP", "L", "P", "INC", "LTD", "LLP", "CORP", "CO", "ET", "AL", "THE", "MA", "CT",
    "CAPITAL", "GLOBAL", "ASSET", "MANAGEMENT", "INVESTMENT", "INVESTMENTS", "INVESTORS",
    "PARTNERS", "FUND", "GROUP", "ADVISORS", "ADVISERS", "STRATEGIC", "FAMILY", "OFFICE",
}


# Issuer-name words that mark a pooled vehicle rather than an operating company.
VEHICLE_WORDS = {"FUND", "TRUST", "LENDING", "CREDIT", "INCOME", "ACQUISITION", "BDC", "TONTINE"}


def _noop(fraction: float, message: str) -> None:
    pass


# ---------------------------------------------------------------- XML helpers

def _local(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _find(node: ET.Element | None, path: str) -> ET.Element | None:
    """Follow a '/'-separated path of local names, ignoring namespaces."""
    for name in path.split("/"):
        if node is None:
            return None
        node = next((child for child in node if _local(child.tag) == name), None)
    return node


def _text(node: ET.Element | None, path: str) -> str | None:
    found = _find(node, path)
    if found is None or found.text is None:
        return None
    value = " ".join(found.text.split())
    return value or None


def _children(node: ET.Element | None, name: str) -> list[ET.Element]:
    return [child for child in node if _local(child.tag) == name] if node is not None else []


def _number(value: str | None) -> float | None:
    try:
        return float(str(value).replace(",", "")) if value not in (None, "") else None
    except ValueError:
        return None


def _iso_date(value: str | None) -> str | None:
    """13D/G XML uses MM/DD/YYYY; Form 4 uses YYYY-MM-DD."""
    if not value:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value[:10], fmt).date().isoformat()
        except ValueError:
            continue
    return value


# -------------------------------------------------------------------- parsers

def parse_schedule_13(xml_text: str) -> dict[str, Any]:
    """Issuer and stake from a structured Schedule 13D or 13G."""
    root = ET.fromstring(xml_text.encode("utf-8"))
    form = _find(root, "formData")
    header = _find(form, "coverPageHeader")
    issuer = _find(header, "issuerInfo")

    persons: list[dict[str, Any]] = []
    for person in _children(_find(form, "reportingPersons"), "reportingPersonInfo"):  # 13D layout
        persons.append({
            "name": _text(person, "reportingPersonName"),
            "shares": _number(_text(person, "aggregateAmountOwned")),
            "percent": _number(_text(person, "percentOfClass")),
        })
    for person in _children(form, "coverPageHeaderReportingPersonDetails"):  # 13G layout
        persons.append({
            "name": _text(person, "reportingPersonName"),
            "shares": _number(_text(person, "reportingPersonBeneficiallyOwnedAggregateNumberOfShares")),
            "percent": _number(_text(person, "classPercent")),
        })

    # Group filers repeat one stake under each entity; the largest is the stake.
    best = max(persons, key=lambda p: (p["percent"] or 0, p["shares"] or 0), default={})
    cusip = _text(issuer, "issuerCusips/issuerCusipNumber")
    return {
        "issuer_name": _text(issuer, "issuerName"),
        "issuer_cik": _text(issuer, "issuerCIK") or _text(issuer, "issuerCik"),
        "cusip": None if not cusip or set(cusip) == {"0"} else cusip,
        "class_title": _text(header, "securitiesClassTitle"),
        "event_date": _iso_date(_text(header, "dateOfEvent") or _text(header, "eventDateRequiresFilingThisStatement")),
        "percent": best.get("percent"),
        "shares": best.get("shares"),
        "reporting_persons": [p["name"] for p in persons if p["name"]],
    }


def parse_form4(xml_text: str) -> dict[str, Any]:
    """Issuer and trades from a Form 4 ownershipDocument."""
    root = ET.fromstring(xml_text.encode("utf-8"))
    issuer = _find(root, "issuer")
    trades: list[dict[str, Any]] = []
    for table, row_name in (("nonDerivativeTable", "nonDerivativeTransaction"), ("derivativeTable", "derivativeTransaction")):
        for row in _children(_find(root, table), row_name):
            shares = _number(_text(row, "transactionAmounts/transactionShares/value"))
            price = _number(_text(row, "transactionAmounts/transactionPricePerShare/value"))
            direction = _text(row, "transactionAmounts/transactionAcquiredDisposedCode/value")
            trades.append({
                "security": _text(row, "securityTitle/value"),
                "derivative": table == "derivativeTable",
                "date": _iso_date(_text(row, "transactionDate/value")),
                "code": _text(row, "transactionCoding/transactionCode"),
                "shares": shares,
                "price": price,
                "direction": direction,  # A = acquired, D = disposed
                "owned_after": _number(_text(row, "postTransactionAmounts/sharesOwnedFollowingTransaction/value")),
            })
    common = [t for t in trades if not t["derivative"]]
    signed = [(t["shares"] or 0) * (1 if t["direction"] == "A" else -1) for t in common]
    value = sum((t["shares"] or 0) * (t["price"] or 0) * (1 if t["direction"] == "A" else -1) for t in common)
    ticker = _text(issuer, "issuerTradingSymbol")
    return {
        "issuer_name": _text(issuer, "issuerName"),
        "issuer_cik": _text(issuer, "issuerCik"),
        "ticker": None if not ticker or ticker.upper() == "NONE" else ticker,
        "transactions": trades,
        "net_shares": sum(signed) if common else None,
        "net_value": value if common else None,
        "owned_after": next((t["owned_after"] for t in reversed(common) if t["owned_after"] is not None), None),
        "event_date": max((t["date"] for t in trades if t["date"]), default=None),
    }


# ------------------------------------------------------------- classification

def manager_brand(manager: str) -> str | None:
    """Distinctive part of a filer name: 'THIRD POINT LLC' -> 'THIRD POINT'."""
    words = [w for w in re.sub(r"[^A-Z0-9 ]", " ", manager.upper()).split() if len(w) > 1]
    words = [w for w in words if w not in GENERIC_WORDS]
    # Two words, not one: 'THIRD' alone would also match 'Third Coast Bancshares'.
    return " ".join(words[:2]) if words else None


def is_affiliated(issuer_name: str | None, investor: dict[str, Any], percent: float | None) -> bool:
    """A manager's own fund or vehicle, not an outside investment.

    Two signals: the issuer carries the manager's brand ('Third Point Private
    Capital Income Fund' for Third Point), or the stake is a majority, which
    for these filers almost always means a seed or control position.
    """
    if percent is not None and percent >= 50:
        return True
    if not issuer_name:
        return False
    issuer = re.sub(r"[^A-Z0-9 ]", " ", issuer_name.upper())
    looks_like_vehicle = bool(VEHICLE_WORDS & set(issuer.split()))
    for brand in {manager_brand(investor.get("manager", "")), manager_brand(investor.get("investor", ""))}:
        if not brand or not re.search(rf"\b{re.escape(brand)}\b", issuer):
            continue
        # A one-word brand is too common to trust alone: Discovery Capital
        # buying Warner Bros. Discovery, or Viking Global buying Viking
        # Therapeutics, are outside stakes. Require a fund-like issuer too.
        if " " in brand or looks_like_vehicle:
            return True
    return False


def stake_filings_in_index(submissions: dict[str, Any], since: str) -> list[dict[str, Any]]:
    """13D/13G/Form 4 entries in a submissions index filed on or after `since`."""
    recent = submissions.get("filings", {}).get("recent", {})
    out = []
    for i, form in enumerate(recent.get("form", [])):
        kind = STAKE_FORMS.get(form)
        if not kind or recent["filingDate"][i] < since:
            continue
        out.append({
            "form": form,
            "kind": kind,
            "amendment": form.endswith("/A"),
            "filing_date": recent["filingDate"][i],
            "accession_number": recent["accessionNumber"][i],
            "primary_document": recent["primaryDocument"][i],
        })
    return out


# --------------------------------------------------------------------- refresh

def refresh_stakes(
    *,
    client: SecClient,
    investors: list[dict[str, Any]],
    root: Path,
    lookback_days: int = 90,
    refresh_index: bool = False,
    progress: ProgressFn = _noop,
    today: date | None = None,
) -> dict[str, Any]:
    """Collect recent stake filings for every investor and write stakes.json.

    Each filing document is fetched once and cached; later runs only open
    filings they have not seen. Pass refresh_index=True when the submissions
    index was not already re-fetched earlier in the same run.
    """
    since = ((today or date.today()) - timedelta(days=lookback_days)).isoformat()
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    fetched = 0
    total = len(investors) or 1

    for n, investor in enumerate(investors):
        progress(n / total, f"Stake filings: {investor.get('investor')}")
        cik = SecClient.clean_cik(investor["cik"])
        try:
            index = client.submissions(cik, refresh=refresh_index)
        except (SecClientError, OSError, ValueError) as exc:
            errors.append(f"{investor['investor']}: could not load filing index: {exc}")
            continue

        for entry in stake_filings_in_index(index, since):
            accession = entry["accession_number"]
            document = entry["primary_document"].split("/")[-1]
            base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}"
            record = {
                **{k: v for k, v in entry.items() if k != "primary_document"},
                "investor": investor.get("investor"),
                "investor_slug": investor.get("slug"),
                "tier": investor.get("tier"),
                "sec_url": f"{base}/{accession}-index.html",
            }
            cache_key = Path("stakes") / f"{accession}.xml"
            if not (client.cache_dir / cache_key).exists():
                fetched += 1
            try:
                xml_text = client.get_text(f"{base}/{document}", cache_key)
                parsed = parse_form4(xml_text) if entry["kind"] == "4" else parse_schedule_13(xml_text)
            except (SecClientError, OSError, ET.ParseError, ValueError) as exc:
                record["error"] = f"could not read filing: {exc}"
                records.append(record)
                continue
            record.update(parsed)
            record["affiliated"] = is_affiliated(record.get("issuer_name"), investor, record.get("percent"))
            # Stakes at or below 5% on a 13D/13G mean the filer has dropped
            # under the reporting threshold: an exit from the disclosed stake.
            record["exit"] = entry["kind"] != "4" and record.get("percent") is not None and record["percent"] <= 5
            records.append(record)

    records.sort(key=lambda r: (r["filing_date"], r["accession_number"]), reverse=True)
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback_days": lookback_days,
        "since": since,
        "filings": records,
        "errors": errors,
    }
    target = root / "data" / "processed" / "stakes.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(output, indent=2), encoding="utf-8")
    progress(1.0, f"Stake filings: {len(records)} in the last {lookback_days} days ({fetched} newly opened).")
    return {"stakes_total": len(records), "stakes_new": fetched, "stakes_errors": errors}


def headline_stakes(records: Iterable[dict[str, Any]], tiers: set[str] | None = None) -> list[dict[str, Any]]:
    """Outside stakes worth reading first: new 13Ds and 13Gs, not amendments, not own funds."""
    tiers = tiers or {"conviction"}
    return [
        r for r in records
        if r.get("kind") in ("13D", "13G") and not r.get("amendment") and not r.get("affiliated")
        and not r.get("error") and (r.get("tier") in tiers or r.get("tier") is None)
    ]
