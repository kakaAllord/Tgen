"""Exports per-teacher timetables to styled .xlsx files."""

from __future__ import annotations

import logging
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from models import TeacherTimetable
from utils import sanitize_filename

logger = logging.getLogger(__name__)

_HEADER_FILL = PatternFill("solid", fgColor="4472C4")
_HEADER_FONT = Font(bold=True, color="FFFFFF")
_TITLE_FONT = Font(bold=True, size=14)
_DAY_FONT = Font(bold=True)
_BORDER = Border(*(Side(style="thin", color="B7B7B7") for _ in range(4)))
_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
_LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)


def export_teacher_timetable(timetable: TeacherTimetable, output_dir: Path) -> Path:
    """Write one teacher's timetable to ``output_dir``, overwriting any existing file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{sanitize_filename(timetable.teacher)}.xlsx"

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Timetable"

    n_cols = len(timetable.time_slots) + 1
    header_row = 2

    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(n_cols, 1))
    title_cell = sheet.cell(row=1, column=1, value=f"{timetable.teacher} - Timetable")
    title_cell.font = _TITLE_FONT
    title_cell.alignment = _CENTER
    sheet.row_dimensions[1].height = 26

    sheet.cell(row=header_row, column=1, value="DAY / TIME")
    for col_idx, time_slot in enumerate(timetable.time_slots, start=2):
        sheet.cell(row=header_row, column=col_idx, value=time_slot)
    for cell in sheet[header_row]:
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = _CENTER
        cell.border = _BORDER

    for row_idx, day in enumerate(timetable.days, start=header_row + 1):
        day_cell = sheet.cell(row=row_idx, column=1, value=day)
        day_cell.font = _DAY_FONT
        day_cell.alignment = _LEFT
        day_cell.border = _BORDER
        for col_idx, time_slot in enumerate(timetable.time_slots, start=2):
            cell = sheet.cell(row=row_idx, column=col_idx, value=timetable.cell(day, time_slot))
            cell.alignment = _CENTER
            cell.border = _BORDER
        sheet.row_dimensions[row_idx].height = 30

    sheet.freeze_panes = f"B{header_row + 1}"
    sheet.column_dimensions["A"].width = 16
    for col_idx in range(2, n_cols + 1):
        sheet.column_dimensions[get_column_letter(col_idx)].width = 24

    workbook.save(path)
    logger.debug("Wrote Excel timetable for %s -> %s", timetable.teacher, path)
    return path


def export_all(timetables: dict[str, TeacherTimetable], output_dir: Path) -> list[Path]:
    """Export every teacher's timetable to ``output_dir``. Returns the written paths."""
    paths = [export_teacher_timetable(timetable, output_dir) for timetable in timetables.values()]
    logger.info("Exported %d Excel timetable(s) to %s", len(paths), output_dir)
    return paths
