"""Entry point for the Teacher Timetable Generator desktop application."""

from __future__ import annotations

import logging
import tkinter as tk

from gui import TimetableApp


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    root = tk.Tk()
    TimetableApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
