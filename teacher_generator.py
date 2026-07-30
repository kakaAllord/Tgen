"""Groups parsed lessons by teacher and builds a clean per-teacher timetable."""

from __future__ import annotations

import logging

from models import Lesson, TeacherTimetable
from utils import time_sort_key, weekday_sort_key

logger = logging.getLogger(__name__)


def group_by_teacher(lessons: list[Lesson]) -> dict[str, list[Lesson]]:
    """Group lessons by their (already-standardized) teacher name."""
    groups: dict[str, list[Lesson]] = {}
    for lesson in lessons:
        groups.setdefault(lesson.teacher, []).append(lesson)
    return groups


def build_teacher_timetables(lessons: list[Lesson]) -> dict[str, TeacherTimetable]:
    """Build one :class:`TeacherTimetable` per teacher found in ``lessons``."""
    grouped = group_by_teacher(lessons)
    timetables = {
        teacher: _build_timetable(teacher, teacher_lessons)
        for teacher, teacher_lessons in grouped.items()
    }
    logger.info("Built timetables for %d teacher(s)", len(timetables))
    return timetables


def list_teacher_names(lessons: list[Lesson]) -> list[str]:
    """Sorted, de-duplicated list of teacher names auto-detected in ``lessons``."""
    return sorted({lesson.teacher for lesson in lessons}, key=str.casefold)


def _build_timetable(teacher: str, lessons: list[Lesson]) -> TeacherTimetable:
    days = sorted({lesson.day for lesson in lessons}, key=weekday_sort_key)
    time_slots = sorted({lesson.time for lesson in lessons}, key=time_sort_key)

    grid: dict[str, dict[str, str]] = {day: {slot: "" for slot in time_slots} for day in days}
    for lesson in lessons:
        entry = f"{lesson.subject} ({lesson.level})"
        existing = grid[lesson.day][lesson.time]
        if not existing:
            grid[lesson.day][lesson.time] = entry
        elif entry not in existing.split(" / "):
            grid[lesson.day][lesson.time] = f"{existing} / {entry}"
            logger.warning(
                "Timetable clash for %s on %s %s: %r",
                teacher,
                lesson.day,
                lesson.time,
                grid[lesson.day][lesson.time],
            )

    sorted_lessons = sorted(
        lessons, key=lambda lesson: (weekday_sort_key(lesson.day), time_sort_key(lesson.time))
    )
    return TeacherTimetable(
        teacher=teacher,
        days=days,
        time_slots=time_slots,
        grid=grid,
        lessons=sorted_lessons,
    )
