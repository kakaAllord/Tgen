"""Extracts structured lessons (Level, Day, Time, Subject, Teacher) from
resolved sheet grids produced by :mod:`reader`.

Each worksheet is one Level. A row whose text contains "TIME/DAY" holds the
time-slot column headers; the first column holds weekdays. Every non-empty,
non-break lesson cell is expected to contain "Subject - Teacher" text (the
separator and spacing vary across the source workbook, e.g. "EET- Mr.
Mathias", "TD-Mr. Marobo", "CA&CAD Mr. Mbelwa").
"""

from __future__ import annotations

import logging
import re

from models import Lesson, SheetGrid
from utils import TIME_DAY_MARKER, is_ignored_cell, normalize_key, normalize_text

logger = logging.getLogger(__name__)

_TITLES = ("Mr", "Mrs", "Ms", "Miss", "Dr", "Prof", "Madam", "Madame")
_TITLE_RE = re.compile(
    r"\b(" + "|".join(_TITLES) + r")\b\.?\s*",
    re.IGNORECASE,
)


def parse_workbook(sheets: list[SheetGrid]) -> list[Lesson]:
    """Parse every sheet (level) into a flat list of lessons."""
    lessons: list[Lesson] = []
    for sheet in sheets:
        lessons.extend(parse_sheet(sheet))
    logger.info("Parsed %d lesson(s) from %d sheet(s)", len(lessons), len(sheets))
    return lessons


def parse_sheet(sheet: SheetGrid) -> list[Lesson]:
    """Parse a single Level's worksheet grid into lessons."""
    rows = sheet.rows
    header_row_indices = _find_header_rows(rows)
    if not header_row_indices:
        logger.warning(
            "Sheet %r has no row containing %r; skipping.", sheet.name, TIME_DAY_MARKER
        )
        return []

    lessons: list[Lesson] = []
    for block_idx, header_row_idx in enumerate(header_row_indices):
        day_col, time_columns = _map_time_columns(rows[header_row_idx])
        block_end = (
            header_row_indices[block_idx + 1]
            if block_idx + 1 < len(header_row_indices)
            else len(rows)
        )
        for row_idx in range(header_row_idx + 1, block_end):
            lessons.extend(_parse_data_row(sheet.name, rows[row_idx], day_col, time_columns))
    return lessons


def _find_header_rows(rows: list[list[str]]) -> list[int]:
    """Row indices whose text contains the TIME/DAY marker (supports multi-block sheets)."""
    indices = []
    for idx, row in enumerate(rows):
        if any(TIME_DAY_MARKER in normalize_key(cell) for cell in row):
            indices.append(idx)
    return indices


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
    row: list[str],
    day_col: int,
    time_columns: list[tuple[int, str]],
) -> list[Lesson]:
    day = normalize_text(row[day_col]) if day_col < len(row) else ""
    if not day or TIME_DAY_MARKER in normalize_key(day):
        return []

    lessons: list[Lesson] = []
    for col_idx, time_label in time_columns:
        cell_text = row[col_idx] if col_idx < len(row) else ""
        if is_ignored_cell(cell_text):
            continue
        subject, teacher = split_subject_teacher(cell_text)
        lessons.append(
            Lesson(
                level=level,
                day=day,
                time=time_label,
                subject=subject,
                teacher=teacher,
                raw_text=cell_text,
            )
        )
    return lessons


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
    """Normalize salutation casing/spacing, e.g. "mr.mathias" -> "Mr. Mathias"."""
    match = _TITLE_RE.match(teacher_text)
    if not match:
        return teacher_text.strip()

    title = match.group(1)
    rest = teacher_text[match.end() :].strip()
    title_cased = title.capitalize()
    separator = " " if title_cased.lower() in {"miss", "madam", "madame"} else ". "
    if not rest:
        return f"{title_cased}{'.' if separator == '. ' else ''}".strip()
    return f"{title_cased}{separator}{rest}"
