"""Extracts structured lessons (Level, Day, Time, Subject, Teacher) from
resolved sheet grids produced by :mod:`reader`.

Each worksheet can hold several trade-specific timetable blocks stacked one
after another (e.g. "LEVEL I" contains a separate Mon-Fri block for EL,
DSCT, MB, ...), each introduced by its own row containing "TIME/DAY". A row
whose text contains "TIME/DAY" holds the time-slot column headers; the first
column holds weekdays. Every non-empty lesson cell is expected to contain
"Subject - Teacher" text (the separator and spacing vary across the source
workbook, e.g. "EET- Mr. Mathias", "TD-Mr. Marobo", "CA&CAD Mr. Mbelwa"), or
be a whole-school activity (PARADE, TEA BREAK, ...) with no teacher.
"""

from __future__ import annotations

import logging
import re

from models import Activity, Lesson, SheetGrid
from utils import (
    TIME_DAY_MARKER,
    classify_activity,
    is_known_weekday,
    is_placeholder_teacher,
    normalize_key,
    normalize_text,
)

logger = logging.getLogger(__name__)

_TITLES = ("Mr", "Mrs", "Ms", "Miss", "Dr", "Prof", "Madam", "Madame")
_TITLE_RE = re.compile(
    r"\b(" + "|".join(_TITLES) + r")\b\.?\s*",
    re.IGNORECASE,
)

#: Matches a trailing parenthesized short code on a block's title row, e.g.
#: "TIME TABLE 2026 ELECTRICAL INSTALATION (EL)" -> "EL".
_TRADE_CODE_RE = re.compile(r"\(([A-Za-z0-9&]{1,12})\)\s*$")
#: How many rows above a "TIME/DAY" header row to search for a title row.
_TITLE_SEARCH_DEPTH = 5


def parse_workbook(sheets: list[SheetGrid]) -> tuple[list[Lesson], list[Activity]]:
    """Parse every sheet (level) into flat lists of lessons and activities."""
    lessons: list[Lesson] = []
    activities: list[Activity] = []
    for sheet in sheets:
        sheet_lessons, sheet_activities = parse_sheet(sheet)
        lessons.extend(sheet_lessons)
        activities.extend(sheet_activities)
    logger.info(
        "Parsed %d lesson(s) and %d activity slot(s) from %d sheet(s)",
        len(lessons),
        len(activities),
        len(sheets),
    )
    return lessons, activities


def parse_sheet(sheet: SheetGrid) -> tuple[list[Lesson], list[Activity]]:
    """Parse a single worksheet's (possibly multi-block) grid."""
    rows = sheet.rows
    header_row_indices = _find_header_rows(rows)
    if not header_row_indices:
        logger.warning(
            "Sheet %r has no row containing %r; skipping.", sheet.name, TIME_DAY_MARKER
        )
        return [], []

    lessons: list[Lesson] = []
    activities: list[Activity] = []
    for block_idx, header_row_idx in enumerate(header_row_indices):
        day_col, time_columns = _map_time_columns(rows[header_row_idx])
        time_grid = tuple(label for _, label in time_columns)
        trade = _detect_trade_code(rows, header_row_idx)
        block_end = (
            header_row_indices[block_idx + 1]
            if block_idx + 1 < len(header_row_indices)
            else len(rows)
        )
        for row_idx in range(header_row_idx + 1, block_end):
            row = rows[row_idx]
            day = normalize_text(row[day_col]) if day_col < len(row) else ""
            if not day or TIME_DAY_MARKER in normalize_key(day) or not is_known_weekday(day):
                # A block's real data is always an unbroken run of weekday
                # rows right after its header - the first row that isn't one
                # (typically a blank spacer, or the next block's title
                # banner bleeding into range(header_row_idx + 1, block_end))
                # marks the end of this block, not a row to skip over.
                break
            row_lessons, row_activities = _parse_data_row(
                sheet.name, trade, day, row, time_columns, time_grid
            )
            lessons.extend(row_lessons)
            activities.extend(row_activities)
    return lessons, activities


def _find_header_rows(rows: list[list[str]]) -> list[int]:
    """Row indices whose text contains the TIME/DAY marker (supports multi-block sheets)."""
    indices = []
    for idx, row in enumerate(rows):
        if any(TIME_DAY_MARKER in normalize_key(cell) for cell in row):
            indices.append(idx)
    return indices


def _detect_trade_code(rows: list[list[str]], header_row_idx: int) -> str | None:
    """Find the block's trade code from a title row above the header, e.g.
    "TIME TABLE 2026 ELECTRICAL INSTALATION (EL)" -> "EL". ``None`` if no
    such title is found nearby.

    Kept separate from ``level`` (the sheet name) rather than merged into one
    label at parse time: whether a lesson should be shown under its precise
    trade code or the coarser level depends on whether it turns out to be
    unique to this block or shared identically across every trade block in
    the level (a combined class) - a decision only ``teacher_generator`` can
    make, once every block has been parsed.
    """
    for offset in range(1, _TITLE_SEARCH_DEPTH + 1):
        row_idx = header_row_idx - offset
        if row_idx < 0:
            break
        for cell in rows[row_idx]:
            match = _TRADE_CODE_RE.search(normalize_text(cell))
            if match:
                return match.group(1).upper()
    return None


def _map_time_columns(header_row: list[str]) -> tuple[int, list[tuple[int, str]]]:
    """Locate the day column and the (column index, time label) pairs from a header row."""
    day_col = 0
    for idx, cell in enumerate(header_row):
        if TIME_DAY_MARKER in normalize_key(cell):
            day_col = idx
            break

    time_columns = [
        (idx, normalize_text(cell))
        for idx, cell in enumerate(header_row)
        if idx != day_col and normalize_text(cell)
    ]
    return day_col, time_columns


def _parse_data_row(
    level: str,
    trade: str | None,
    day: str,
    row: list[str],
    time_columns: list[tuple[int, str]],
    time_grid: tuple[str, ...],
) -> tuple[list[Lesson], list[Activity]]:
    lessons: list[Lesson] = []
    activities: list[Activity] = []
    for col_idx, time_label in time_columns:
        cell_text = row[col_idx] if col_idx < len(row) else ""
        text = normalize_text(cell_text)
        if not text:
            continue

        activity = classify_activity(text)
        if activity is not None:
            label, recurring = activity
            activities.append(
                Activity(
                    level=level,
                    day=day,
                    time=time_label,
                    label=label,
                    time_grid=time_grid,
                    recurring=recurring,
                )
            )
            continue

        subject, teacher = split_subject_teacher(text)
        if is_placeholder_teacher(teacher):
            # "Maths. TC", "Core- TC", etc. - the sheet never names a real
            # teacher for this slot, so there's no one to attribute it to;
            # drop it rather than inventing a fake "TC"/"Unknown" teacher.
            continue
        lessons.append(
            Lesson(
                level=level,
                trade=trade,
                day=day,
                time=time_label,
                subject=subject,
                teacher=teacher,
                raw_text=text,
                time_grid=time_grid,
            )
        )
    return lessons, activities


def split_subject_teacher(cell_text: str) -> tuple[str, str]:
    """Split a lesson cell ("Subject - Teacher") into (subject, teacher).

    Looks for a salutation (Mr./Mrs./Ms./Dr./...) to anchor the split, since
    the separator between subject and teacher is inconsistent in the source
    data (" - ", "-", or a bare space). Falls back to splitting on the last
    "-" when no salutation is present, and finally to treating the whole
    cell as the subject with an "Unknown" teacher.
    """
    text = normalize_text(cell_text)
    match = _TITLE_RE.search(text)
    if match:
        subject = text[: match.start()].rstrip(" -–—")
        teacher = _standardize_teacher(text[match.start() :])
        return subject.strip(), teacher

    if "-" in text:
        subject, _, teacher_raw = text.rpartition("-")
        subject = subject.strip()
        teacher = teacher_raw.strip()
        if subject and teacher:
            return subject, teacher

    logger.warning("Could not split subject/teacher from cell text: %r", cell_text)
    return text, "Unknown"


def _standardize_teacher(teacher_text: str) -> str:
    """Normalize salutation casing/spacing and name casing, e.g.
    "mr.mathias" -> "Mr. Mathias", so the same teacher spelled with
    inconsistent case in different blocks (e.g. "Mr. isack" vs "Mr. Isack")
    always collapses to one entry instead of splitting into two.
    """
    match = _TITLE_RE.match(teacher_text)
    if not match:
        return teacher_text.strip()

    title = match.group(1)
    rest = teacher_text[match.end() :].strip()
    title_cased = title.capitalize()
    separator = " " if title_cased.lower() in {"miss", "madam", "madame"} else ". "
    if not rest:
        return f"{title_cased}{'.' if separator == '. ' else ''}".strip()
    # Capitalize fully-lowercase words (e.g. "isack" -> "Isack"); leave
    # anything already mixed/upper case alone (e.g. "Wickleaf", "AW" initials).
    normalized_rest = " ".join(
        word.capitalize() if word.islower() else word for word in rest.split()
    )
    return f"{title_cased}{separator}{normalized_rest}"
