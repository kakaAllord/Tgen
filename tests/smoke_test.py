"""End-to-end smoke test: builds a synthetic master workbook, runs it through
reader -> parser -> teacher_generator -> pdf_export/excel_export, and checks
the pipeline behaves as expected.

Not a full unit-test suite - a fast confidence check that the wiring works.
Run with: python tests/smoke_test.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import excel_export
import pdf_export
from generate_sample import build_sample_workbook
from parser import parse_workbook, split_subject_teacher
from reader import read_workbook
from teacher_generator import build_teacher_timetables, list_teacher_names
from utils import sanitize_filename

TEST_OUTPUT_DIR = Path(__file__).parent / "_test_output"


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    failures: list[str] = []

    def check(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)
            print(f"FAIL: {message}")
        else:
            print(f"OK:   {message}")

    # 1. Unit-level check of the trickiest bit: subject/teacher splitting.
    cases = {
        "EET- Mr. Mathias": ("EET", "Mr. Mathias"),
        "TD-Mr. Marobo": ("TD", "Mr. Marobo"),
        "CA&CAD Mr. Mbelwa": ("CA&CAD", "Mr. Mbelwa"),
    }
    for text, expected in cases.items():
        result = split_subject_teacher(text)
        check(result == expected, f"split_subject_teacher({text!r}) == {expected!r} (got {result!r})")

    # 2. Build a synthetic master workbook mimicking the real structure.
    sample_path = build_sample_workbook()
    original_hash = _hash_file(sample_path)
    check(sample_path.exists(), "sample workbook created")

    # 3. Run the full pipeline.
    sheets = read_workbook(sample_path)
    check(len(sheets) == 2, f"read 2 sheets (got {len(sheets)})")

    lessons = parse_workbook(sheets)
    check(len(lessons) > 0, f"parsed at least one lesson (got {len(lessons)})")

    unknown_lessons = [lesson for lesson in lessons if lesson.teacher == "Unknown"]
    check(not unknown_lessons, f"no lessons fell back to 'Unknown' teacher (got {len(unknown_lessons)})")

    ignored_texts = {"PARADE", "TEA BREAK", "GAMES", ""}
    check(
        not any(lesson.raw_text.strip().upper() in ignored_texts for lesson in lessons),
        "PARADE / TEA BREAK / GAMES / empty cells were excluded",
    )

    teacher_names = list_teacher_names(lessons)
    expected_teachers = {"Mr. Mathias", "Mr. Marobo", "Mrs. Juma", "Ms. Kway", "Mr. Mbelwa"}
    check(
        expected_teachers.issubset(set(teacher_names)),
        f"all expected teachers detected (got {teacher_names})",
    )

    timetables = build_teacher_timetables(lessons)
    check(len(timetables) == len(teacher_names), "one timetable built per teacher")

    # 4. Export and verify files land where expected.
    pdf_dir = TEST_OUTPUT_DIR / "PDFs"
    excel_dir = TEST_OUTPUT_DIR / "Excel"
    pdf_paths = pdf_export.export_all(timetables, pdf_dir)
    excel_paths = excel_export.export_all(timetables, excel_dir)

    check(len(pdf_paths) == len(timetables), "one PDF exported per teacher")
    check(len(excel_paths) == len(timetables), "one Excel file exported per teacher")
    check(all(p.exists() and p.stat().st_size > 0 for p in pdf_paths), "all PDF files exist and are non-empty")
    check(
        all(p.exists() and p.stat().st_size > 0 for p in excel_paths),
        "all Excel files exist and are non-empty",
    )

    expected_pdf = pdf_dir / f"{sanitize_filename('Mr. Mathias')}.pdf"
    check(expected_pdf.exists(), f"expected PDF path exists: {expected_pdf}")

    # 5. Regenerating must overwrite, not duplicate.
    before_count = len(list(pdf_dir.glob('*.pdf')))
    pdf_export.export_all(timetables, pdf_dir)
    after_count = len(list(pdf_dir.glob('*.pdf')))
    check(before_count == after_count, "regenerating overwrites files instead of duplicating them")

    # 6. The master workbook must never be modified.
    check(_hash_file(sample_path) == original_hash, "master workbook bytes unchanged after full pipeline run")

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
