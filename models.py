"""Shared, typed data structures used across the Timetable Generator modules."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Lesson:
    """A single lesson extracted from the master workbook.

    Represents one occupied cell in a level's timetable sheet: a specific
    subject taught by a specific teacher, on a specific day/time, for a
    specific level.
    """

    level: str
    day: str
    time: str
    subject: str
    teacher: str
    raw_text: str


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
