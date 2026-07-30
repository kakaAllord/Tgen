"""Exports per-teacher timetables to styled, landscape .pdf files."""

from __future__ import annotations

import logging
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from models import TeacherTimetable
from utils import sanitize_filename

logger = logging.getLogger(__name__)

_PAGE_SIZE = landscape(A4)
_MARGIN = 24


def export_teacher_timetable(timetable: TeacherTimetable, output_dir: Path) -> Path:
    """Write one teacher's timetable to ``output_dir``, overwriting any existing file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{sanitize_filename(timetable.teacher)}.pdf"

    doc = SimpleDocTemplate(
        str(path),
        pagesize=_PAGE_SIZE,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        topMargin=_MARGIN,
        bottomMargin=_MARGIN,
        title=f"{timetable.teacher} Timetable",
    )

    styles = getSampleStyleSheet()
    elements = [
        Paragraph(f"{timetable.teacher} - Timetable", styles["Title"]),
        Spacer(1, 12),
    ]

    if not timetable.days or not timetable.time_slots:
        elements.append(Paragraph("No lessons found for this teacher.", styles["Normal"]))
        doc.build(elements)
        return path

    header_style = ParagraphStyle(
        "TimetableHeader", parent=styles["Normal"], fontSize=9, leading=11,
        textColor=colors.white, alignment=1,
    )
    cell_style = ParagraphStyle("TimetableCell", parent=styles["Normal"], fontSize=8, leading=10)
    day_style = ParagraphStyle("TimetableDay", parent=cell_style, fontName="Helvetica-Bold")

    header_row = ["DAY / TIME", *timetable.time_slots]
    table_data = [[Paragraph(text, header_style) for text in header_row]]
    for day in timetable.days:
        row = [Paragraph(day, day_style)]
        row.extend(
            Paragraph(timetable.cell(day, slot) or "", cell_style) for slot in timetable.time_slots
        )
        table_data.append(row)

    n_cols = len(header_row)
    available_width = _PAGE_SIZE[0] - 2 * _MARGIN
    day_col_width = max(70.0, available_width * 0.12)
    other_col_width = (available_width - day_col_width) / max(n_cols - 1, 1)
    col_widths = [day_col_width] + [other_col_width] * (n_cols - 1)

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4472C4")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#B7B7B7")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F2F2")]),
            ]
        )
    )
    elements.append(table)

    doc.build(elements)
    logger.debug("Wrote PDF timetable for %s -> %s", timetable.teacher, path)
    return path


def export_all(timetables: dict[str, TeacherTimetable], output_dir: Path) -> list[Path]:
    """Export every teacher's timetable to ``output_dir``. Returns the written paths."""
    paths = [export_teacher_timetable(timetable, output_dir) for timetable in timetables.values()]
    logger.info("Exported %d PDF timetable(s) to %s", len(paths), output_dir)
    return paths
