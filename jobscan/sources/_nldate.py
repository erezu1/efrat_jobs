"""Small date helpers shared by the university sources (English + Dutch dates).

Underscore-prefixed so main.load_sources() does not treat it as a source.
"""
from __future__ import annotations

import re
from datetime import date

MONTHS = {
    # English
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
    # Dutch
    "januari": 1, "februari": 2, "maart": 3, "mei": 5, "juni": 6, "juli": 7,
    "augustus": 8, "oktober": 10, "okt": 10, "mrt": 3,
}
_MON = "|".join(sorted(MONTHS, key=len, reverse=True))

_TEXTUAL = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th|e)?\s+(?:of\s+)?({_MON})\.?\s*,?\s+(\d{{4}})\b", re.I)
_TEXTUAL_US = re.compile(rf"\b({_MON})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\s*,?\s+(\d{{4}})\b", re.I)
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DMY = re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b")

DEADLINE_WORDS = re.compile(
    r"(?i)deadline|closing date|closes on|apply (?:before|until|by|no later)|applications? .{0,40}(?:before|until|by)"
    r"|sluitingsdatum|sluit op|solliciteren kan tot|reageren kan tot|uiterlijk|vóór|voor \d|tot en met|t/m"
)


def _mk(y: int, m: int, d: int) -> str | None:
    try:
        return date(y, m, d).isoformat()
    except ValueError:
        return None


def parse_date(s: str | None) -> str | None:
    """Parse the first date in s ("15 september 2026", "Sept 15, 2026", "15-09-2026", ISO)."""
    if not s:
        return None
    m = _ISO.search(s)
    if m:
        return _mk(int(m[1]), int(m[2]), int(m[3]))
    m = _TEXTUAL.search(s)
    if m:
        return _mk(int(m[3]), MONTHS[m[2].lower()], int(m[1]))
    m = _TEXTUAL_US.search(s)
    if m:
        return _mk(int(m[3]), MONTHS[m[1].lower()], int(m[2]))
    m = _DMY.search(s)
    if m:
        return _mk(int(m[3]), int(m[2]), int(m[1]))
    return None


def find_deadline(text: str | None) -> str | None:
    """Find a date that appears shortly after a deadline keyword in free text."""
    if not text:
        return None
    for m in DEADLINE_WORDS.finditer(text):
        d = parse_date(text[m.start(): m.end() + 60])
        if d:
            return d
    return None
