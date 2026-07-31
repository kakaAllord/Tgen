"""Small shared helpers: constants, filename sanitizing, weekday/time ordering."""

from __future__ import annotations

import re

#: Institution name printed at the top of every exported timetable.
INSTITUTION_NAME = "KOROGWE DVTC"

#: Cell text values that must be ignored when extracting lessons.
#: Matched case-insensitively after collapsing whitespace/punctuation.
IGNORED_CELL_KEYWORDS: frozenset[str] = frozenset(
    {
        "PARADE",
        "TEA BREAK",
        "TEABREAK",
        "TEA-BREAK",
        "BREAK",
        "LUNCH",
        "LUNCH BREAK",
        "GAMES",
    }
)

#: Header marker that identifies the row holding time-slot column labels.
#: Stored already-normalized (see `normalize_key`) since it is always compared
#: against normalized cell text.
TIME_DAY_MARKER = "TIME DAY"

WEEKDAY_ORDER: dict[str, int] = {
    "MONDAY": 0,
    "TUESDAY": 1,
    "WEDNESDAY": 2,
    "THURSDAY": 3,
    "FRIDAY": 4,
    "SATURDAY": 5,
    "SUNDAY": 6,
}

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def normalize_text(value: object) -> str:
    """Coerce a cell value to a stripped, whitespace-collapsed string."""
    if value is None:
        return ""
    text = str(value).strip()
    return re.sub(r"\s+", " ", text)


def normalize_key(value: object) -> str:
    """Normalize text for keyword/lookup comparisons (case/punctuation-insensitive)."""
    text = normalize_text(value).upper()
    return re.sub(r"[\s\-_/]+", " ", text).strip()


def is_ignored_cell(value: object) -> bool:
    """True for empty cells or cells matching an ignored keyword (PARADE, TEA BREAK, ...)."""
    text = normalize_text(value)
    if not text:
        return True
    return normalize_key(text) in IGNORED_CELL_KEYWORDS


def weekday_sort_key(day: str) -> tuple[int, str]:
    """Sort key placing known weekdays in order; unknown days sort after, alphabetically."""
    order = WEEKDAY_ORDER.get(normalize_key(day), len(WEEKDAY_ORDER))
    return (order, normalize_key(day))


_TIME_START_RE = re.compile(r"(\d{1,2})[:.](\d{2})")


def time_sort_key(time_slot: str) -> tuple[int, str]:
    """Sort key ordering time-slot labels by their first HH:MM occurrence."""
    match = _TIME_START_RE.search(time_slot)
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
        return (hour * 60 + minute, time_slot)
    return (24 * 60, time_slot)


def sanitize_filename(name: str) -> str:
    """Make a string safe to use as a Windows filename (without extension)."""
    cleaned = _INVALID_FILENAME_CHARS.sub("", name).strip().strip(".")
    return cleaned or "Unknown"
