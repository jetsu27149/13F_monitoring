"""Incremental refresh of the local 13F dataset.

``refresh_data.py`` rebuilds everything by re-parsing every cached filing. That
is the right behaviour for a cold start, but it is wasteful once ``data/raw/``
is populated: those rows are already parsed and enriched. This module reuses
them and downloads only the filings that are missing locally, which is what the
dashboard's "Check filings" button needs in order to feel immediate.

The functions here are deliberately free of HTTP-server concerns so they can be
driven from a background thread, from ``refresh_data.py``, or from a test with a
stubbed SEC client.
"""

from __future__ import annotations

import csv
import gc
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable

from thirteenf.analytics import build_dashboard_data
from thirteenf.parser import parse_information_table
from thirteenf.sec_client import SecClient, SecClientError

# A progress reporter receives (fraction_complete, human_readable_message).
ProgressFn = Callable[[float, str], None]

PLACEHOLDER_CONTACT = "contact@example.com"


def load_env_file(path: Path) -> None:
    """Load KEY=value lines from a .env file without overriding the real environment.

    Both the dashboard server and the command-line refresh read keys this way, so
    a scheduled job and a button click see the same SEC_USER_AGENT.
    """
    if not path.exists():
        return
    import os

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


def noop_progress(fraction: float, message: str) -> None:
    """Default progress sink."""


def raw_dir(root: Path) -> Path:
    return root / "data" / "raw"


def processed_dir(root: Path) -> Path:
    return root / "data" / "processed"


def user_agent_looks_unset(user_agent: str) -> bool:
    """True when the SEC user agent is still the shipped placeholder.

    SEC rejects clients that do not identify themselves with a working contact
    address, and the resulting 403 is easy to mistake for "no new filings".
    """
    return not user_agent or PLACEHOLDER_CONTACT in user_agent


def local_accessions(root: Path) -> dict[str, set[str]]:
    """Map investor slug to the accession numbers already stored under data/raw.

    Read from filenames rather than file contents: the raw tree is close to a
    gigabyte, and knowing *what* exists should not require loading all of it.
    """
    found: dict[str, set[str]] = defaultdict(set)
    base = raw_dir(root)
    if not base.is_dir():
        return found
    for slug_dir in base.iterdir():
        if not slug_dir.is_dir():
            continue
        for path in slug_dir.glob("*.json"):
            # Filenames are "{report_date}_{accession_number}.json".
            _, _, accession = path.stem.partition("_")
            if accession:
                found[slug_dir.name].add(accession)
    return found


def load_local_rows(root: Path, progress: ProgressFn = noop_progress) -> tuple[list[dict[str, Any]], list[str]]:
    """Load every already-parsed holding row from data/raw, one filing set per quarter.

    A manager can file more than once for the same quarter: an original 13F-HR
    and later 13F-HR/A amendments. Each lands as its own file, so loading them
    all would count that quarter twice. Resolve them per (manager, report date):
    see resolve_amendments.
    """
    errors: list[str] = []
    base = raw_dir(root)
    if not base.is_dir():
        return [], errors

    groups: dict[tuple[str, str], list[list[dict[str, Any]]]] = defaultdict(list)
    paths = sorted(path for slug_dir in base.iterdir() if slug_dir.is_dir() for path in slug_dir.glob("*.json"))
    total = len(paths) or 1
    for index, path in enumerate(paths):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            errors.append(f"Could not read cached filing {path.name}: {exc}")
            continue
        if isinstance(data, list) and data:
            report_date = path.stem.partition("_")[0]
            groups[(path.parent.name, report_date)].append(data)
        if index % 25 == 0:
            progress(index / total, f"Loading local filings ({index}/{total})")

    rows: list[dict[str, Any]] = []
    for filings in groups.values():
        rows.extend(resolve_amendments(filings))
    return rows, errors


def resolve_amendments(filings: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Combine one manager's filings for one quarter into a single set of rows.

    Filings are applied in filing-date order. A 13F-HR/A is either a
    restatement, which replaces the whole report, or a "new holdings"
    amendment, which only adds positions left out of the original. The type
    sits in the filing's cover page, which is not stored here, so it is
    inferred from size: an amendment with at least half the rows of what it
    amends is treated as a restatement, anything smaller as additions.
    """
    ordered = sorted(filings, key=lambda rows: (rows[0].get("filing_date") or "", rows[0].get("accession_number") or ""))
    current = list(ordered[0])
    for later in ordered[1:]:
        if len(later) >= 0.5 * len(current):
            current = list(later)
        else:
            current.extend(later)
    return current


def enrich_rows(investor: dict[str, Any], filing: Any, parsed_rows: Iterable[dict[str, Any]], info_table_file: str) -> list[dict[str, Any]]:
    """Attach investor and filing identity to each parsed holding row."""
    return [
        {
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
        for row in parsed_rows
    ]


def download_missing_filings(
    client: SecClient,
    investor: dict[str, Any],
    *,
    root: Path,
    known: dict[str, set[str]],
    quarters: int = 4,
    errors: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Fetch and store any recent filings for one investor not already on disk.

    Returns a list of {report_date, accession_number, rows} for what was added.
    """
    errors = errors if errors is not None else []
    slug = investor["slug"]
    seen = known.get(slug, set())
    added: list[dict[str, Any]] = []

    try:
        filings = client.recent_13f_filings(investor["cik"], limit=quarters, refresh=True)
    except (SecClientError, OSError) as exc:
        errors.append(f"{investor['investor']}: could not load submissions: {exc}")
        return added

    for filing in filings:
        if filing.accession_number in seen:
            continue
        try:
            xml_text, info_table_file = client.information_table_xml(filing, refresh=False)
            parsed_rows = parse_information_table(xml_text)
        except (SecClientError, OSError, ValueError) as exc:
            errors.append(f"{investor['investor']} {filing.report_date}: could not parse filing: {exc}")
            continue

        rows = enrich_rows(investor, filing, parsed_rows, info_table_file)
        if not rows:
            errors.append(f"{investor['investor']} {filing.report_date}: filing contained no holding rows.")
            continue

        destination = raw_dir(root) / slug / f"{filing.report_date}_{filing.accession_number}.json"
        write_json(destination, rows)
        seen.add(filing.accession_number)
        added.append(
            {
                "report_date": filing.report_date,
                "accession_number": filing.accession_number,
                "filing_date": filing.filing_date,
                "rows": len(rows),
            }
        )

    known[slug] = seen
    return added


def rebuild_outputs(
    root: Path,
    investors: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    *,
    errors: list[str],
    out: Path | None = None,
) -> dict[str, Any]:
    """Rebuild dashboard.json and the CSV exports from the given rows."""
    dashboard = build_dashboard_data(investors, rows, mode="live", errors=errors)
    target = out or (processed_dir(root) / "dashboard.json")
    write_json(target, dashboard)
    write_csv(processed_dir(root) / "holdings.csv", dashboard["holdings"])
    write_csv(processed_dir(root) / "changes.csv", dashboard["changes"])
    write_csv(processed_dir(root) / "watchlist.csv", dashboard["watchlist"])
    return dashboard


def run_incremental_refresh(
    *,
    root: Path,
    investors: list[dict[str, Any]],
    user_agent: str,
    quarters: int = 4,
    progress: ProgressFn = noop_progress,
) -> dict[str, Any]:
    """Download any new filings for `investors`, then rebuild the dashboard.

    `investors` should already be narrowed to the ones worth checking. Raises
    nothing for per-investor failures; those are collected into the returned
    `errors` list so one bad filer cannot abort the run.
    """
    errors: list[str] = []
    known = local_accessions(root)
    client = SecClient(cache_dir=root / "data" / "cache", user_agent=user_agent)

    downloaded: list[dict[str, Any]] = []
    total = len(investors) or 1
    for index, investor in enumerate(investors):
        progress(0.05 + 0.55 * (index / total), f"Downloading {investor.get('investor', investor.get('slug'))}")
        added = download_missing_filings(
            client,
            investor,
            root=root,
            known=known,
            quarters=quarters,
            errors=errors,
        )
        for item in added:
            downloaded.append({**item, "investor": investor.get("investor"), "investor_slug": investor.get("slug")})

    # 13D/13G/Form 4 arrive between 13F seasons, so check them on every run,
    # across the whole registry. Each investor's filing index was re-fetched
    # just above (or by the check that preceded this run), so reuse it.
    stakes = run_stakes_step(root, investors, client, errors, progress)

    if not downloaded:
        progress(1.0, "No new 13F filings to download.")
        return {
            "downloaded": [],
            "errors": errors,
            "rebuilt": False,
            "filings_added": 0,
            "rows_added": 0,
            **stakes,
        }

    progress(0.62, f"Downloaded {len(downloaded)} filing(s). Loading local history...")
    rows, load_errors = load_local_rows(root, progress=lambda f, m: progress(0.62 + 0.28 * f, m))
    errors.extend(load_errors)

    progress(0.92, "Rebuilding dashboard...")
    dashboard = rebuild_outputs(root, investors_all(root, investors), rows, errors=errors)

    # The row list can be several gigabytes for a full 20-quarter history, and
    # this runs inside a long-lived server process, so drop it eagerly.
    summary_counts = (len(dashboard.get("holdings", [])), len(dashboard.get("watchlist", [])))
    del rows, dashboard
    gc.collect()

    progress(1.0, f"Added {len(downloaded)} filing(s).")
    return {
        "downloaded": downloaded,
        "errors": errors,
        "rebuilt": True,
        "filings_added": len(downloaded),
        "rows_added": sum(item["rows"] for item in downloaded),
        "holdings": summary_counts[0],
        "watchlist": summary_counts[1],
        **stakes,
    }


def run_stakes_step(root: Path, investors: list[dict[str, Any]], client: SecClient, errors: list[str], progress: ProgressFn) -> dict[str, Any]:
    """Refresh stakes.json; a failure here must not cost the 13F refresh."""
    from thirteenf.stakes import refresh_stakes

    try:
        result = refresh_stakes(
            client=client,
            investors=investors_all(root, investors),
            root=root,
            progress=lambda f, m: progress(0.56 + 0.05 * f, m),
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Stake filings skipped: {exc}")
        return {"stakes_total": None, "stakes_new": 0}
    errors.extend(result.pop("stakes_errors", []))
    return result


def investors_all(root: Path, fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Always rebuild against the full registry.

    The dashboard is cross-investor: concentration, shared ownership and the
    watchlist are all computed across the whole set. Rebuilding from only the
    refreshed subset would silently drop everyone else from the output.
    """
    registry = root / "investors.json"
    try:
        return json.loads(registry.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)

    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(flatten_row(row))


def flatten_row(row: dict[str, Any]) -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, value in row.items():
        flattened[key] = json.dumps(value) if isinstance(value, (list, dict)) else value
    return flattened
