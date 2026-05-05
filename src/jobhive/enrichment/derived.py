"""Derive enrichment columns from existing fields.

Pure functions — given a row's existing data (location string, title), infer
fields like `is_remote` and `seniority`. Cheap to run, no network.
"""

from __future__ import annotations

import re

REMOTE_KEYWORDS = ("remote", "anywhere", "distributed", "work from home", "wfh", "telework")
ONSITE_KEYWORDS = ("onsite", "on-site", "in-office", "in person")

_SENIORITY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("INTERN", re.compile(r"\b(intern|internship|co-?op|trainee|apprentice)\b", re.I)),
    ("EXECUTIVE", re.compile(r"\b(chief|cxo|cto|cfo|coo|ceo|cmo|cpo|c-suite|svp\b|evp\b)", re.I)),
    ("DIRECTOR", re.compile(r"\b(director|head of|vp(?!\s*of\s*engineering\s*intern)|vice\s*president)\b", re.I)),
    ("PRINCIPAL", re.compile(r"\b(principal|distinguished|fellow)\b", re.I)),
    ("STAFF", re.compile(r"\bstaff\b", re.I)),
    ("SENIOR", re.compile(r"\b(senior|sr\.?|lead|advanced)\b", re.I)),
    ("ENTRY", re.compile(r"\b(junior|jr\.?|associate|entry[- ]?level|graduate|new[- ]?grad|early[- ]?career)\b", re.I)),
]


def infer_is_remote(location: object) -> bool | None:
    """Return True if the location string clearly indicates remote, False if it
    clearly indicates onsite, None otherwise. Accepts NaN/None gracefully.
    """
    if not isinstance(location, str) or not location.strip():
        return None
    lower = location.lower()
    if any(kw in lower for kw in REMOTE_KEYWORDS):
        return True
    if any(kw in lower for kw in ONSITE_KEYWORDS):
        return False
    return None


def infer_seniority(title: object) -> str | None:
    """Classify a job title into one of the `Seniority` levels."""
    if not isinstance(title, str) or not title.strip():
        return None
    for level, pattern in _SENIORITY_PATTERNS:
        if pattern.search(title):
            return level
    return "MID"  # default for unmarked titles


# --- Salary parsing ---------------------------------------------------------

_SALARY_RANGE_RE = re.compile(
    r"""
    (?P<sym1>[$£€¥]|CA\$|US\$|A\$|NZ\$|HK\$|S\$|R\$)?\s*
    (?P<n1>\d[\d,. ]*)\s*
    (?P<u1>[KMkm]|thousand|million)?
    \s*(?:[-–—~]|to)\s*
    (?P<sym2>[$£€¥]|CA\$|US\$|A\$|NZ\$|HK\$|S\$|R\$)?\s*
    (?P<n2>\d[\d,. ]*)\s*
    (?P<u2>[KMkm]|thousand|million)?
    """,
    re.VERBOSE,
)
_SALARY_SINGLE_RE = re.compile(
    r"""
    (?P<sym>[$£€¥]|CA\$|US\$|A\$)?\s*
    (?P<n>\d[\d,. ]{2,})\s*
    (?P<u>[KMkm]|thousand|million)?
    """,
    re.VERBOSE,
)


def _parse_salary_token(num: str, unit: str | None) -> float | None:
    """Convert a number token + optional unit suffix to a float amount."""
    cleaned = num.replace(",", "").replace(" ", "").rstrip(".")
    if cleaned.count(".") > 1:
        cleaned = cleaned.replace(".", "", cleaned.count(".") - 1)
    try:
        value = float(cleaned)
    except ValueError:
        return None
    multiplier = 1.0
    if unit:
        u = unit.lower()
        if u.startswith("k") or u == "thousand":
            multiplier = 1_000
        elif u.startswith("m") or u == "million":
            multiplier = 1_000_000
    return value * multiplier


def parse_salary_range(text: object) -> tuple[float | None, float | None]:
    """Extract `(min, max)` from a salary summary string.

    Handles `$257K - $335K`, `CA$400K – CA$500K`, `60,000 - 80,000`,
    `€80k–€120k`, etc. Returns (None, None) when nothing parseable.
    """
    if not isinstance(text, str) or not text.strip():
        return (None, None)
    match = _SALARY_RANGE_RE.search(text)
    if match:
        lo = _parse_salary_token(match.group("n1"), match.group("u1"))
        hi = _parse_salary_token(match.group("n2"), match.group("u2"))
        if lo is not None and hi is not None and lo > hi:
            lo, hi = hi, lo
        return (lo, hi)
    match = _SALARY_SINGLE_RE.search(text)
    if match:
        value = _parse_salary_token(match.group("n"), match.group("u"))
        return (value, value)
    return (None, None)
