"""Small shared helpers: constants, filename sanitizing, weekday/time ordering."""

from __future__ import annotations

import re

#: Institution name printed at the top of every exported timetable.
INSTITUTION_NAME = "KOROGWE DVTC"

#: Whole-school, non-teaching activities that recur at the same time every
#: day - the source workbook typically only writes the label on one day
#: (usually Monday) and leaves the same column blank on the rest, trusting
#: the reader to infer it repeats daily. Matched case-insensitively after
#: collapsing whitespace/punctuation.
RECURRING_ACTIVITY_KEYWORDS: frozenset[str] = frozenset(
    {
        "PARADE",
        "TEA BREAK",
        "TEABREAK",
        "TEA-BREAK",
        "BREAK",
        "LUNCH",
        "LUNCH BREAK",
    }
)

#: Whole-school, non-teaching activities tied to a specific day (e.g. a
#: Friday-only assembly slot) - rendered exactly where the sheet places them,
#: never inferred onto other days.
ONE_OFF_ACTIVITY_KEYWORDS: frozenset[str] = frozenset(
    {
        "GAMES",
        "CLEANLINESS",
        "PRAYER SESSION",
        "SPORTS",
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


def classify_activity(value: object) -> tuple[str, bool] | None:
    """Classify a non-blank cell as a whole-school activity, if it is one.

    Returns ``(label, recurring)`` where ``recurring`` is True for a daily
    activity (TEA BREAK, PARADE, ...) and False for a day-specific one
    (CLEANLINESS, SPORTS, ...); returns ``None`` for an ordinary lesson cell.
    """
    text = normalize_text(value)
    if not text:
        return None
    key = normalize_key(text)
    if key in RECURRING_ACTIVITY_KEYWORDS:
        return (text, True)
    if key in ONE_OFF_ACTIVITY_KEYWORDS:
        return (text, False)
    return None


def is_known_weekday(day: str) -> bool:
    """True if ``day`` matches (a prefix of) a known weekday name."""
    return weekday_sort_key(day)[0] != len(WEEKDAY_ORDER)


def weekday_sort_key(day: str) -> tuple[int, str]:
    """Sort key placing known weekdays in order; unknown days sort after, alphabetically.

    The source workbook abbreviates weekdays inconsistently (``Mon``, ``Tues``,
    ``Wedn``, ``Thur``, ``Fri``), so exact lookup isn't enough - match any
    prefix of a known full weekday name (e.g. ``WEDN`` -> ``WEDNESDAY``).
    """
    key = normalize_key(day)
    for name, order in WEEKDAY_ORDER.items():
        if key and name.startswith(key):
            return (order, key)
    return (len(WEEKDAY_ORDER), key)


_TIME_START_RE = re.compile(r"(\d{1,2})[:.](\d{2})\s*(AM|PM)?", re.IGNORECASE)


def time_sort_key(time_slot: str) -> tuple[int, str]:
    """Sort key ordering time-slot labels by their first HH:MM occurrence.

    Handles a trailing AM/PM (e.g. "01.30PM-02.15PM") by converting to 24-hour
    time - without this, "01.30PM" sorts as if it were 1:30 AM, landing
    afternoon periods before the morning ones.
    """
    match = _TIME_START_RE.search(time_slot)
    if not match:
        return (24 * 60, time_slot)
    hour, minute, meridiem = int(match.group(1)), int(match.group(2)), match.group(3)
    if meridiem:
        meridiem = meridiem.upper()
        if meridiem == "PM" and hour != 12:
            hour += 12
        elif meridiem == "AM" and hour == 12:
            hour = 0
    return (hour * 60 + minute, time_slot)


def fit_row_heights(
    n_data_rows: int,
    available_height: float,
    header_height: float,
    min_data_row_height: float,
    max_data_row_height: float,
) -> float:
    """Compute a per-data-row height that spreads ``available_height`` across
    ``n_data_rows``, so a timetable with few lessons still fills the page
    instead of leaving it mostly blank.

    Stays within ``[min_data_row_height, max_data_row_height]``: many rows
    fall back to the minimum (may run past one page, same as before this
    existed); few rows are capped at the maximum, leaving the leftover space
    as bottom padding rather than stretching rows absurdly tall.
    """
    if n_data_rows <= 0:
        return min_data_row_height
    ideal = (available_height - header_height) / n_data_rows
    return max(min_data_row_height, min(ideal, max_data_row_height))


def sanitize_filename(name: str) -> str:
    """Make a string safe to use as a Windows filename (without extension)."""
    cleaned = _INVALID_FILENAME_CHARS.sub("", name).strip().strip(".")
    return cleaned or "Unknown"
