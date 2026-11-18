from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import requests


SEC_DATA_BASE = "https://data.sec.gov"
SEC_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"


class SecClientError(RuntimeError):
    """Raised when EDGAR data cannot be fetched or parsed."""


@dataclass(frozen=True)
class Filing:
    cik: str
    accession_number: str
    form: str
    filing_date: str
    report_date: str
    primary_document: str
    archive_dir: str
    sec_url: str


class SecClient:
    """Small SEC EDGAR client with on-disk caching and polite throttling."""

    def __init__(
        self,
        cache_dir: Path,
        user_agent: str,
        sleep_seconds: float = 0.15,
        timeout_seconds: int = 30,
    ) -> None:
        self.cache_dir = cache_dir
        self.user_agent = user_agent
        self.sleep_seconds = sleep_seconds
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
            }
        )

    @staticmethod
    def clean_cik(cik: str) -> str:
        return str(cik).strip().zfill(10)

    @staticmethod
    def cik_for_archive(cik: str) -> str:
        return str(int(cik))

    @staticmethod
    def accession_dir(accession_number: str) -> str:
        return accession_number.replace("-", "")

    def get_json(self, url: str, cache_key: Path, refresh: bool = False) -> dict[str, Any]:
        path = self.cache_dir / cache_key
        if path.exists() and not refresh:
            return json.loads(path.read_text(encoding="utf-8"))

        data = self._request(url).json()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return data

    def get_text(self, url: str, cache_key: Path, refresh: bool = False) -> str:
        path = self.cache_dir / cache_key
        if path.exists() and not refresh:
            return path.read_text(encoding="utf-8")

        text = self._request(url).text
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return text

    def _request(self, url: str) -> requests.Response:
        time.sleep(self.sleep_seconds)
        response = self.session.get(url, timeout=self.timeout_seconds)
        if response.status_code >= 400:
            raise SecClientError(f"SEC request failed {response.status_code}: {url}")
        return response

    def submissions(self, cik: str, refresh: bool = False) -> dict[str, Any]:
        cik10 = self.clean_cik(cik)
        url = f"{SEC_DATA_BASE}/submissions/CIK{cik10}.json"
        return self.get_json(url, Path("submissions") / f"CIK{cik10}.json", refresh)

    def recent_13f_filings(
        self,
        cik: str,
        limit: int = 8,
        include_amendments: bool = True,
        refresh: bool = False,
        latest_per_period: bool = True,
    ) -> list[Filing]:
        """13F filings for the `limit` most recent report periods, newest first.

        With latest_per_period (the default) each period yields only its most
        recent filing, which is what "is there anything newer?" needs. To store
        a quarter, pass latest_per_period=False: a 13F-HR/A is often a "new
        holdings" amendment listing only positions the original left out, so
        keeping just the amendment loses the rest of the report.
        """
        cik10 = self.clean_cik(cik)
        data = self.submissions(cik10, refresh=refresh)
        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accessions = recent.get("accessionNumber", [])
        filing_dates = recent.get("filingDate", [])
        report_dates = recent.get("reportDate", [])
        primary_documents = recent.get("primaryDocument", [])

        filings: list[Filing] = []
        allowed_forms = {"13F-HR", "13F-HR/A"} if include_amendments else {"13F-HR"}
        for index, form in enumerate(forms):
            if form not in allowed_forms:
                continue
            accession = accessions[index]
            archive_dir = self.accession_dir(accession)
            cik_archive = self.cik_for_archive(cik10)
            sec_url = f"https://www.sec.gov/Archives/edgar/data/{cik_archive}/{archive_dir}/{accession}-index.html"
            filings.append(
                Filing(
                    cik=cik10,
                    accession_number=accession,
                    form=form,
                    filing_date=filing_dates[index],
                    report_date=report_dates[index],
                    primary_document=primary_documents[index],
                    archive_dir=archive_dir,
                    sec_url=sec_url,
                )
            )

        if not latest_per_period:
            periods = sorted({filing.report_date for filing in filings}, reverse=True)[:limit]
            keep = set(periods)
            return sorted(
                (filing for filing in filings if filing.report_date in keep),
                key=lambda item: (item.report_date, item.filing_date, item.accession_number),
                reverse=True,
            )

        latest_by_report_date: dict[str, Filing] = {}
        for filing in filings:
            existing = latest_by_report_date.get(filing.report_date)
            if existing is None or filing.filing_date >= existing.filing_date:
                latest_by_report_date[filing.report_date] = filing

        deduped = sorted(latest_by_report_date.values(), key=lambda item: item.report_date, reverse=True)
        return deduped[:limit]

    def filing_index(self, filing: Filing, refresh: bool = False) -> dict[str, Any]:
        cik_archive = self.cik_for_archive(filing.cik)
        url = f"{SEC_ARCHIVES_BASE}/{cik_archive}/{filing.archive_dir}/index.json"
        cache_key = Path("indexes") / filing.cik / f"{filing.accession_number}.json"
        return self.get_json(url, cache_key, refresh=refresh)

    def information_table_xml(self, filing: Filing, refresh: bool = False) -> tuple[str, str]:
        index = self.filing_index(filing, refresh=refresh)
        items = index.get("directory", {}).get("item", [])
        names = [item.get("name", "") for item in items if item.get("name", "").lower().endswith(".xml")]
        preferred = sorted(
            names,
            key=lambda name: (
                "info" not in name.lower() and "table" not in name.lower(),
                name.lower() == filing.primary_document.lower(),
                name.lower(),
            ),
        )

        errors: list[str] = []
        for name in preferred:
            url = self.archive_file_url(filing, name)
            cache_key = Path("filings") / filing.cik / filing.archive_dir / name
            text = self.get_text(url, cache_key, refresh=refresh)
            if is_information_table_xml(text):
                return text, name
            errors.append(name)

        raise SecClientError(
            f"No information table XML found for {filing.accession_number}. Checked: {', '.join(errors)}"
        )

    def archive_file_url(self, filing: Filing, filename: str) -> str:
        cik_archive = self.cik_for_archive(filing.cik)
        return f"{SEC_ARCHIVES_BASE}/{cik_archive}/{filing.archive_dir}/{filename}"


def is_information_table_xml(text: str) -> bool:
    try:
        root = ET.fromstring(text.encode("utf-8"))
    except ET.ParseError:
        return False

    root_name = strip_namespace(root.tag).lower()
    if root_name == "informationtable":
        return True
    return any(strip_namespace(child.tag).lower() == "infotable" for child in root)


def strip_namespace(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag
