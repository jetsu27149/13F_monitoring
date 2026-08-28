from __future__ import annotations

import random
from datetime import date
from typing import Any


SAMPLE_SECURITIES = [
    ("MICROSOFT CORP", "594918104", "COM"),
    ("AMAZON COM INC", "023135106", "COM"),
    ("ALPHABET INC", "02079K305", "CAP STK CL A"),
    ("META PLATFORMS INC", "30303M102", "CL A"),
    ("NVIDIA CORP", "67066G104", "COM"),
    ("BOOKING HOLDINGS INC", "09857L108", "COM"),
    ("VISA INC", "92826C839", "COM CL A"),
    ("MASTERCARD INC", "57636Q104", "CL A"),
    ("HILTON WORLDWIDE HLDGS INC", "43300A203", "COM"),
    ("CHIPOTLE MEXICAN GRILL INC", "169656105", "COM"),
    ("GE AEROSPACE", "369604301", "COM"),
    ("APOLLO GLOBAL MGMT INC", "03769M106", "COM"),
    ("VERTIV HOLDINGS CO", "92537N108", "CL A"),
    ("ENERGY TRANSFER LP", "29273V100", "COM UT LTD PTN"),
    ("ROCKET COS INC", "77311W101", "COM CL A"),
    ("CRH PLC", "12626K203", "ORD"),
    ("DOLLAR GENERAL CORP", "256677105", "COM"),
    ("UNITEDHEALTH GROUP INC", "91324P102", "COM"),
    ("COUPANG INC", "22266T109", "CL A"),
    ("SHOPIFY INC", "82509L107", "CL A"),
    ("TAIWAN SEMICONDUCTOR MFG LTD", "874039100", "SPONSORED ADS"),
    ("SPDR S&P 500 ETF TRUST", "78462F103", "UNIT"),
    ("ISHARES 20+ YEAR TREASURY BOND ETF", "464287432", "COM"),
    ("BROADCOM INC", "11135F101", "COM"),
    ("UBER TECHNOLOGIES INC", "90353T100", "COM"),
    ("SERVICENOW INC", "81762P102", "COM"),
    ("SALESFORCE INC", "79466L302", "COM"),
    ("ELI LILLY & CO", "532457108", "COM"),
]

REPORT_DATES = [
    date(2025, 12, 31),
    date(2025, 9, 30),
    date(2025, 6, 30),
    date(2025, 3, 31),
]


def generate_sample_holdings(investors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Generate deterministic demo rows when live SEC access is unavailable."""

    rows: list[dict[str, Any]] = []
    rng = random.Random(13)
    for investor_index, investor in enumerate(investors):
        breadth = 18
        if investor["slug"] == "tudor":
            breadth = 60
        elif investor["slug"] in {"pershing-square", "baupost", "tci"}:
            breadth = 10
        elif investor["slug"] in {"duquesne", "cooperman", "durable"}:
            breadth = 24

        base_indices = [(investor_index * 3 + offset) % len(SAMPLE_SECURITIES) for offset in range(breadth)]
        for quarter_index, report_date in enumerate(REPORT_DATES):
            filing_date = date(report_date.year + (1 if report_date.month == 12 else 0), 2 if report_date.month == 12 else report_date.month + 2, 14)
            for holding_rank, security_index in enumerate(base_indices):
                issuer, cusip, title = SAMPLE_SECURITIES[security_index]
                if quarter_index > 0 and rng.random() < 0.08:
                    continue
                weight_bias = max(1, breadth - holding_rank) / breadth
                value = (rng.uniform(20, 650) * 1_000_000 * weight_bias) * (1 + quarter_index * rng.uniform(-0.12, 0.1))
                shares = max(1000, value / rng.uniform(20, 450))
                rows.append(
                    {
                        "investor_slug": investor["slug"],
                        "investor": investor["investor"],
                        "manager": investor["manager"],
                        "cik": investor["cik"],
                        "accession_number": f"SAMPLE-{investor['slug']}-{report_date.isoformat()}",
                        "form": "13F-HR",
                        "filing_date": filing_date.isoformat(),
                        "report_date": report_date.isoformat(),
                        "information_table_file": "sample",
                        "sec_url": f"https://www.sec.gov/edgar/browse/?CIK={int(investor['cik'])}",
                        "issuer": issuer,
                        "title_of_class": title,
                        "cusip": cusip,
                        "figi": None,
                        "value_reported": round(value, 0),
                        "value_thousands": round(value / 1000, 0),
                        "value_usd": round(value, 0),
                        "shares": round(shares, 0),
                        "share_type": "SH",
                        "put_call": None,
                        "investment_discretion": "SOLE",
                        "other_manager": None,
                        "voting_sole": round(shares, 0),
                        "voting_shared": 0,
                        "voting_none": 0,
                    }
                )
    return rows
