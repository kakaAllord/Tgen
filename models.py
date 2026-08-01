"""Shared, typed data structures used across the Timetable Generator modules."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Lesson:
    """A single lesson extracted from the master workbook.

    Represents one occupied cell in a level's timetable sheet: a specific
    subject taught by a specific teacher, on a specific day/time, for a
    specific level.

    ``level`` is the worksheet's level (e.g. "LEVEL I"). ``trade`` is the
    specific trade block within that level's sheet (e.g. "EL"), when one
    could be detected from the block's title row - ``None`` for lessons
    shared across every trade block (general subjects taught to the whole
    level combined), where the trade wouldn't be meaningful.

    ``time_grid`` is the full ordered tuple of time-column labels from the
    header row this lesson came from - it identifies which "shift" (e.g. a
    morning timetable vs. a separate evening one) the lesson belongs to, so
    a teacher's blank/free periods are only ever filled in from the same
    shift they actually teach in, never a disjoint one.
    """

    level: str
    trade: str | None
    day: str
    time: str
    subject: str
    teacher: str
    raw_text: str
    time_grid: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Activity:
    """A whole-school, non-teaching activity cell (PARADE, TEA BREAK, ...).

    Not attributed to any teacher - rendered into every teacher timetable
    that shares the same ``time_grid`` instead.
    """

    level: str
    day: str
    time: str
    label: str
    time_grid: tuple[str, ...]
    recurring: bool


@dataclass(slots=True)
class SheetGrid:
    """The fully-resolved (merged cells expanded) contents of one worksheet."""

    name: str
    rows: list[list[str]]


@dataclass(slots=True)
class TeacherTimetable:
    """A single teacher's generated timetable, ready for export."""

    teacher: str
    days: list[str]
    time_slots: list[str]
    # grid[day][time_slot] -> cell text (may be empty string)
    grid: dict[str, dict[str, str]] = field(default_factory=dict)
    lessons: list[Lesson] = field(default_factory=list)

    def cell(self, day: str, time_slot: str) -> str:
        return self.grid.get(day, {}).get(time_slot, "")
