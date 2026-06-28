"""Output normalization to match the CSV conventions.

IMPORTANT: this layer only *formats* a value the model already decided on
(zero-padding a date, stripping 'Rs'/commas from a number). It never locates or
chooses a value from raw text, so the extraction remains model-driven, not
rule-based.
"""
from __future__ import annotations

import re


def normalize_value(value: str) -> str:
    """Keep digits only (monthly rent as a plain integer)."""
    if not value:
        return ""
    digits = re.sub(r"[^\d]", "", str(value))
    return digits


def normalize_days(value: str) -> str:
    """Keep digits only (renewal notice in days)."""
    if not value:
        return ""
    return re.sub(r"[^\d]", "", str(value))


def normalize_date(value: str) -> str:
    """Coerce to zero-padded DD.MM.YYYY without validating the calendar.

    The ground-truth labels contain impossible dates (e.g. 31.02.2011) that are
    derived as start+term, so we must NOT reject 'invalid' day/month values.
    """
    if not value:
        return ""
    s = str(value).strip()
    parts = re.split(r"[.\-/\s]+", s)
    parts = [p for p in parts if p]
    if len(parts) != 3:
        return s  # unknown shape; leave as-is
    d, m, y = parts
    # Handle YYYY.MM.DD ordering just in case the model flips it.
    if len(d) == 4 and len(y) <= 2:
        d, y = y, d
    if len(y) == 2:
        y = "20" + y
    try:
        d = f"{int(d):02d}"
        m = f"{int(m):02d}"
        y = f"{int(y):04d}"
    except ValueError:
        return s
    return f"{d}.{m}.{y}"


def normalize_name(value: str) -> str:
    """Trim surrounding and collapse internal whitespace for a party name."""
    if not value:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def normalize_result(raw: dict) -> dict:
    """Apply field-appropriate normalization to a raw extraction dict."""
    return {
        "agreement_value": normalize_value(raw.get("agreement_value", "")),
        "agreement_start_date": normalize_date(raw.get("agreement_start_date", "")),
        "agreement_end_date": normalize_date(raw.get("agreement_end_date", "")),
        "renewal_notice_days": normalize_days(raw.get("renewal_notice_days", "")),
        "party_one": normalize_name(raw.get("party_one", "")),
        "party_two": normalize_name(raw.get("party_two", "")),
    }
