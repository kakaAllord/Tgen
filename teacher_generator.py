"""Groups parsed lessons by teacher and builds a clean per-teacher timetable."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from models import Activity, Lesson, TeacherTimetable
from utils import normalize_key, time_sort_key, weekday_sort_key

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _GridInfo:
    """Everything a single ``time_grid`` (a "shift") needs to fill in the
    blanks and whole-school activities for every teacher who belongs to it.
    """

    days: set[str] = field(default_factory=set)
    #: time -> label, applied to every day in ``days`` (TEA BREAK, PARADE, ...)
    recurring: dict[str, str] = field(default_factory=dict)
    #: (day, time) -> label, applied only where the sheet actually wrote it
    one_off: dict[tuple[str, str], str] = field(default_factory=dict)


def group_by_teacher(lessons: list[Lesson]) -> dict[str, list[Lesson]]:
    """Group lessons by their (already-standardized) teacher name."""
    groups: dict[str, list[Lesson]] = {}
    for lesson in lessons:
        groups.setdefault(lesson.teacher, []).append(lesson)
    return groups


def build_teacher_timetables(
    lessons: list[Lesson], activities: list[Activity] | None = None
) -> dict[str, TeacherTimetable]:
    """Build one :class:`TeacherTimetable` per teacher found in ``lessons``.

    A timetable's day/time-slot axes are the full grid of the "shift"
    (``time_grid``) the teacher's lessons belong to - not the whole school -
    so a teacher's free periods show up as blank cells instead of the row or
    column disappearing, without pulling in an unrelated shift's columns
    (e.g. a separate evening-class time grid) that teacher never appears in.
    """
    activities = activities or []
    grouped = group_by_teacher(lessons)
    grid_lookup = _build_grid_lookup(lessons, activities)

    timetables = {
        teacher: _build_timetable(teacher, teacher_lessons, grid_lookup)
        for teacher, teacher_lessons in grouped.items()
    }
    logger.info("Built timetables for %d teacher(s)", len(timetables))
    return timetables


def list_teacher_names(lessons: list[Lesson]) -> list[str]:
    """Sorted, de-duplicated list of teacher names auto-detected in ``lessons``."""
    return sorted({lesson.teacher for lesson in lessons}, key=str.casefold)


def _build_grid_lookup(
    lessons: list[Lesson], activities: list[Activity]
) -> dict[tuple[str, ...], _GridInfo]:
    lookup: dict[tuple[str, ...], _GridInfo] = {}
    for lesson in lessons:
        lookup.setdefault(lesson.time_grid, _GridInfo()).days.add(lesson.day)
    for activity in activities:
        info = lookup.setdefault(activity.time_grid, _GridInfo())
        info.days.add(activity.day)
        if activity.recurring:
            info.recurring.setdefault(activity.time, activity.label)
        else:
            info.one_off[(activity.day, activity.time)] = activity.label
    return lookup


def _build_timetable(
    teacher: str,
    lessons: list[Lesson],
    grid_lookup: dict[tuple[str, ...], _GridInfo],
) -> TeacherTimetable:
    grids_used = {lesson.time_grid for lesson in lessons}
    days = sorted(
        {day for grid in grids_used for day in grid_lookup[grid].days}, key=weekday_sort_key
    )
    time_slots = sorted({slot for grid in grids_used for slot in grid}, key=time_sort_key)

    grid: dict[str, dict[str, str]] = {day: {slot: "" for slot in time_slots} for day in days}

    by_cell: dict[tuple[str, str], list[Lesson]] = {}
    for lesson in lessons:
        by_cell.setdefault((lesson.day, lesson.time), []).append(lesson)
    for (day, time), cell_lessons in by_cell.items():
        grid[day][time] = _render_cell(teacher, day, time, cell_lessons)

    for time_grid in grids_used:
        info = grid_lookup[time_grid]
        for slot in time_grid:
            if slot not in time_slots:
                continue
            recurring_label = info.recurring.get(slot)
            for day in info.days:
                if day not in days or grid[day][slot]:
                    continue
                if recurring_label:
                    grid[day][slot] = recurring_label
                    continue
                one_off_label = info.one_off.get((day, slot))
                if one_off_label:
                    grid[day][slot] = one_off_label

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


def _render_cell(teacher: str, day: str, time: str, cell_lessons: list[Lesson]) -> str:
    """Render every lesson a teacher has at one (day, time) into one cell.

    Several trade blocks in the same level often repeat the exact same
    general-subject lesson verbatim (one combined class taught to the whole
    level at once) - those collapse into a single entry under the plain
    level. A lesson unique to one trade block (e.g. a trade-specific
    practical) is labelled with that trade instead. Genuinely different
    lessons landing in the same slot are a real double-booking and are kept
    side by side with a logged warning.
    """
    groups: dict[str, list[Lesson]] = {}
    order: list[str] = []
    for lesson in cell_lessons:
        key = normalize_key(lesson.subject)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(lesson)

    entries = []
    for key in order:
        group = groups[key]
        representative = group[0]
        if len(group) == 1 and representative.trade:
            short_level = re.sub(r"(?i)\blevel\b", "", representative.level).strip()
            level_label = f"{representative.trade}-{short_level}" if short_level else representative.trade
        else:
            level_label = representative.level
        entries.append(f"{representative.subject} ({level_label})")

    if len(entries) > 1:
        logger.warning(
            "Timetable clash for %s on %s %s: %r", teacher, day, time, " / ".join(entries)
        )
    return " / ".join(entries)
