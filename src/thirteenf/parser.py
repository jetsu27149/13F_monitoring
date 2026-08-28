from __future__ import annotations

from statistics import median
from typing import Any
from xml.etree import ElementTree as ET


def parse_information_table(xml_text: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text.encode("utf-8"))
    rows: list[dict[str, Any]] = []

    for info_table in iter_named(root, "infoTable"):
        value_reported = parse_float(child_text(info_table, "value"))
        shares = parse_float(nested_text(info_table, ["shrsOrPrnAmt", "sshPrnamt"]))
        row = {
            "issuer": child_text(info_table, "nameOfIssuer"),
            "title_of_class": child_text(info_table, "titleOfClass"),
            "cusip": child_text(info_table, "cusip"),
            "figi": child_text(info_table, "figi"),
            "value_reported": value_reported,
            "value_thousands": None,
            "value_usd": None,
            "value_scale": None,
            "shares": shares,
            "share_type": nested_text(info_table, ["shrsOrPrnAmt", "sshPrnamtType"]),
            "put_call": child_text(info_table, "putCall"),
            "investment_discretion": child_text(info_table, "investmentDiscretion"),
            "other_manager": child_text(info_table, "otherManager"),
            "voting_sole": parse_float(nested_text(info_table, ["votingAuthority", "Sole"])),
            "voting_shared": parse_float(nested_text(info_table, ["votingAuthority", "Shared"])),
            "voting_none": parse_float(nested_text(info_table, ["votingAuthority", "None"])),
        }
        if row["issuer"] and row["cusip"]:
            rows.append(row)

    value_scale = infer_value_scale(rows)
    for row in rows:
        reported = row["value_reported"]
        if reported is None:
            continue
        row["value_scale"] = value_scale
        row["value_usd"] = reported * value_scale
        row["value_thousands"] = row["value_usd"] / 1000

    return rows


def infer_value_scale(rows: list[dict[str, Any]]) -> int:
    """Infer whether a filing reports values in dollars or legacy thousands.

    Most modern 13F XML files report dollars, but some current filings still
    contain values that line up with the older thousands convention. We infer
    the scale from non-option share rows: dollars produce plausible share
    prices, while thousands produce values/shares that are roughly 1/1000th of
    the share price.
    """

    ratios = []
    for row in rows:
        value = row.get("value_reported")
        shares = row.get("shares")
        title = str(row.get("title_of_class") or "").lower()
        if not value or not shares or row.get("put_call") or "option" in title:
            continue
        ratios.append(float(value) / float(shares))

    if not ratios:
        return 1

    return 1000 if median(ratios) < 1 else 1


def iter_named(root: ET.Element, local_name: str) -> list[ET.Element]:
    return [element for element in root.iter() if strip_namespace(element.tag) == local_name]


def child_text(parent: ET.Element, local_name: str) -> str | None:
    for child in parent:
        if strip_namespace(child.tag) == local_name:
            return clean_text(child.text)
    return None


def nested_text(parent: ET.Element, path: list[str]) -> str | None:
    cursor = parent
    for local_name in path:
        match = None
        for child in cursor:
            if strip_namespace(child.tag) == local_name:
                match = child
                break
        if match is None:
            return None
        cursor = match
    return clean_text(cursor.text)


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def parse_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def strip_namespace(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag
