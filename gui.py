"""Tkinter desktop UI for the Teacher Timetable Generator.

Long-running work (reading the workbook, exporting files) runs on background
threads; results are marshalled back to the Tk main thread through a queue
polled with ``root.after`` so widgets are only ever touched from the main
thread.
"""

from __future__ import annotations

import logging
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import excel_export
import pdf_export
from models import TeacherTimetable
from parser import parse_workbook
from reader import read_workbook
from teacher_generator import build_teacher_timetables, list_teacher_names

logger = logging.getLogger(__name__)

APP_VERSION = "1.0.0"

HELP_TEXT = """Getting Started

1. Click "Select Master Excel..." and choose your timetable workbook
   (.xlsx or .xlsm). Every worksheet is read automatically; each
   worksheet is treated as one Level.

2. Wait for the status bar to say "Loaded N lesson(s) across
   M teacher(s)." The teacher list on the left will fill in.

3. Find a teacher:
     - Type into "Search Teacher" to filter the list as you type.
     - Or just scroll and click a name in the list.

4. Generate timetables:
     - "Generate All" creates a PDF and an Excel file for every
       teacher found in the workbook.
     - Select one teacher, then click "Generate Selected Teacher"
       (or just double-click their name) to generate only that one.

5. Click "Open Output Folder" to see the generated files.

Where files are saved

    <folder of your workbook>\\Output\\PDFs\\<Teacher Name>.pdf
    <folder of your workbook>\\Output\\Excel\\<Teacher Name>.xlsx

Good to know

    - The master workbook is read-only: this app never modifies it.
    - Regenerating a teacher overwrites their previous file, so it's
      always safe to run "Generate All" again after updating the
      workbook.
    - Cells reading PARADE, TEA BREAK, GAMES, or left empty are
      skipped automatically.
    - Lesson cells are expected in the form "Subject - Teacher",
      e.g. "EET- Mr. Mathias" or "CA&CAD Mr. Mbelwa".
"""

ABOUT_TEXT = (
    f"Teacher Timetable Generator\nVersion {APP_VERSION}\n\n"
    "Reads a master Excel timetable workbook and generates a clean, "
    "individual PDF and Excel timetable for every teacher."
)


class TimetableApp:
    """Main application window."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Teacher Timetable Generator")
        self.root.geometry("680x560")
        self.root.minsize(600, 480)

        self.master_path: Path | None = None
        self.output_dir: Path | None = None
        self.timetables: dict[str, TeacherTimetable] = {}
        self.all_teacher_names: list[str] = []

        self._queue: queue.Queue[tuple[str, object]] = queue.Queue()

        self._build_menu()
        self._build_widgets()
        self._set_generation_enabled(False)
        self.root.after(100, self._poll_queue)

    # ---------------------------------------------------------------- menu

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Getting Started", command=self._show_help)
        help_menu.add_separator()
        help_menu.add_command(label="About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menubar)

    def _show_help(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("Getting Started")
        window.geometry("560x520")
        window.transient(self.root)

        text = tk.Text(window, wrap=tk.WORD, padx=12, pady=12, font=("Segoe UI", 10))
        text.insert("1.0", HELP_TEXT)
        text.config(state=tk.DISABLED)
        text.pack(fill=tk.BOTH, expand=True)

        ttk.Button(window, text="Close", command=window.destroy).pack(pady=8)
        window.focus_set()

    def _show_about(self) -> None:
        messagebox.showinfo("About Teacher Timetable Generator", ABOUT_TEXT)

    # ------------------------------------------------------------------ UI

    def _build_widgets(self) -> None:
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")

        root_frame = ttk.Frame(self.root, padding=12)
        root_frame.pack(fill=tk.BOTH, expand=True)
        root_frame.columnconfigure(0, weight=1)
        root_frame.rowconfigure(3, weight=1)

        # -- Master workbook selection -----------------------------------
        select_frame = ttk.Frame(root_frame)
        select_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        select_frame.columnconfigure(1, weight=1)

        self.select_btn = ttk.Button(
            select_frame, text="Select Master Excel...", command=self._on_select_master
        )
        self.select_btn.grid(row=0, column=0, sticky="w")

        self.master_label_var = tk.StringVar(value="No workbook selected")
        ttk.Label(select_frame, textvariable=self.master_label_var, foreground="#555555").grid(
            row=0, column=1, sticky="w", padx=(10, 0)
        )

        # -- Actions --------------------------------------------------------
        actions_frame = ttk.Frame(root_frame)
        actions_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        self.generate_all_btn = ttk.Button(
            actions_frame, text="Generate All", command=self._on_generate_all
        )
        self.generate_all_btn.pack(side=tk.LEFT)

        self.generate_selected_btn = ttk.Button(
            actions_frame, text="Generate Selected Teacher", command=self._on_generate_selected
        )
        self.generate_selected_btn.pack(side=tk.LEFT, padx=(8, 0))

        self.open_output_btn = ttk.Button(
            actions_frame, text="Open Output Folder", command=self._on_open_output_folder
        )
        self.open_output_btn.pack(side=tk.LEFT, padx=(8, 0))

        ttk.Button(actions_frame, text="Help", command=self._show_help).pack(
            side=tk.RIGHT
        )

        # -- Search -----------------------------------------------------
        search_frame = ttk.Frame(root_frame)
        search_frame.grid(row=2, column=0, sticky="ew", pady=(0, 4))
        search_frame.columnconfigure(1, weight=1)

        ttk.Label(search_frame, text="Search Teacher:").grid(row=0, column=0, sticky="w")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh_teacher_list())
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        search_entry.grid(row=0, column=1, sticky="ew", padx=(8, 0))

        # -- Teacher list -------------------------------------------------
        list_frame = ttk.Frame(root_frame)
        list_frame.grid(row=3, column=0, sticky="nsew", pady=(0, 8))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self.teacher_listbox = tk.Listbox(list_frame, activestyle="dotbox", exportselection=False)
        self.teacher_listbox.grid(row=0, column=0, sticky="nsew")
        self.teacher_listbox.bind("<Double-Button-1>", lambda _e: self._on_generate_selected())

        scrollbar = ttk.Scrollbar(
            list_frame, orient=tk.VERTICAL, command=self.teacher_listbox.yview
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.teacher_listbox.configure(yscrollcommand=scrollbar.set)

        # -- Progress + status --------------------------------------------
        self.progress = ttk.Progressbar(root_frame, mode="determinate")
        self.progress.grid(row=4, column=0, sticky="ew", pady=(0, 4))

        self.status_var = tk.StringVar(value="Select a master Excel workbook to begin.")
        ttk.Label(root_frame, textvariable=self.status_var, foreground="#555555").grid(
            row=5, column=0, sticky="w"
        )

    # ------------------------------------------------------------- helpers

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _set_busy(self, busy: bool) -> None:
        state = tk.DISABLED if busy else tk.NORMAL
        self.select_btn.config(state=state)
        self.open_output_btn.config(state=state)
        if busy:
            self._set_generation_enabled(False)
        else:
            self._set_generation_enabled(bool(self.timetables))

    def _set_generation_enabled(self, enabled: bool) -> None:
        state = tk.NORMAL if enabled else tk.DISABLED
        self.generate_all_btn.config(state=state)
        self.generate_selected_btn.config(state=state)

    def _refresh_teacher_list(self) -> None:
        query = self.search_var.get().strip().lower()
        names = (
            [name for name in self.all_teacher_names if query in name.lower()]
            if query
            else self.all_teacher_names
        )
        self.teacher_listbox.delete(0, tk.END)
        for name in names:
            self.teacher_listbox.insert(tk.END, name)

    def _get_selected_teacher(self) -> str | None:
        selection = self.teacher_listbox.curselection()
        if not selection:
            return None
        return self.teacher_listbox.get(selection[0])

    # ------------------------------------------------------------- actions

    def _on_select_master(self) -> None:
        path_str = filedialog.askopenfilename(
            title="Select Master Excel Workbook",
            filetypes=[("Excel Workbook", "*.xlsx *.xlsm"), ("All files", "*.*")],
        )
        if not path_str:
            return

        self.master_path = Path(path_str)
        self.output_dir = self.master_path.parent / "Output"
        self.master_label_var.set(self.master_path.name)
        self.timetables = {}
        self.all_teacher_names = []
        self._refresh_teacher_list()
        self._set_generation_enabled(False)

        self._set_status(f"Loading {self.master_path.name} ...")
        self._set_busy(True)
        self.progress.config(mode="indeterminate")
        self.progress.start(10)

        threading.Thread(target=self._load_workbook_worker, args=(self.master_path,), daemon=True).start()

    def _load_workbook_worker(self, path: Path) -> None:
        try:
            sheets = read_workbook(path)
            lessons = parse_workbook(sheets)
            timetables = build_teacher_timetables(lessons)
            self._queue.put(("loaded", (lessons, timetables)))
        except Exception as exc:  # noqa: BLE001 - surfaced to the user via the GUI
            logger.exception("Failed to load workbook %s", path)
            self._queue.put(("error", f"Failed to read workbook:\n{exc}"))

    def _on_generate_all(self) -> None:
        if not self.timetables or self.output_dir is None:
            messagebox.showwarning("Nothing to generate", "Select a master workbook first.")
            return

        self._set_busy(True)
        self.progress.config(mode="determinate", maximum=len(self.timetables), value=0)
        self._set_status("Generating timetables for all teachers...")

        threading.Thread(
            target=self._generate_all_worker,
            args=(list(self.timetables.values()), self.output_dir),
            daemon=True,
        ).start()

    def _generate_all_worker(self, timetables: list[TeacherTimetable], output_dir: Path) -> None:
        pdf_dir = output_dir / "PDFs"
        excel_dir = output_dir / "Excel"
        try:
            for idx, timetable in enumerate(timetables, start=1):
                pdf_export.export_teacher_timetable(timetable, pdf_dir)
                excel_export.export_teacher_timetable(timetable, excel_dir)
                self._queue.put(("progress", idx))
            self._queue.put(("done_all", len(timetables)))
        except Exception as exc:  # noqa: BLE001 - surfaced to the user via the GUI
            logger.exception("Failed to generate all timetables")
            self._queue.put(("error", f"Failed to generate timetables:\n{exc}"))

    def _on_generate_selected(self) -> None:
        teacher = self._get_selected_teacher()
        if teacher is None or self.output_dir is None:
            messagebox.showwarning("No teacher selected", "Please select a teacher from the list.")
            return

        timetable = self.timetables[teacher]
        self._set_busy(True)
        self.progress.config(mode="indeterminate")
        self.progress.start(10)
        self._set_status(f"Generating timetable for {teacher}...")

        threading.Thread(
            target=self._generate_one_worker, args=(timetable, self.output_dir), daemon=True
        ).start()

    def _generate_one_worker(self, timetable: TeacherTimetable, output_dir: Path) -> None:
        try:
            pdf_export.export_teacher_timetable(timetable, output_dir / "PDFs")
            excel_export.export_teacher_timetable(timetable, output_dir / "Excel")
            self._queue.put(("done_one", timetable.teacher))
        except Exception as exc:  # noqa: BLE001 - surfaced to the user via the GUI
            logger.exception("Failed to generate timetable for %s", timetable.teacher)
            self._queue.put(("error", f"Failed to generate timetable:\n{exc}"))

    def _on_open_output_folder(self) -> None:
        if self.output_dir is None:
            messagebox.showwarning("No output folder", "Select a master workbook first.")
            return
        self.output_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(self.output_dir)  # noqa: S606 - Windows-only desktop app

    # --------------------------------------------------------- queue polling

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                self._handle_message(kind, payload)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _handle_message(self, kind: str, payload: object) -> None:
        if kind == "loaded":
            lessons, timetables = payload  # type: ignore[misc]
            self.timetables = timetables
            self.all_teacher_names = list_teacher_names(lessons)
            self._refresh_teacher_list()
            self.progress.stop()
            self.progress.config(mode="determinate", value=0)
            self._set_busy(False)
            self._set_status(
                f"Loaded {len(lessons)} lesson(s) across {len(timetables)} teacher(s)."
            )

        elif kind == "progress":
            self.progress.config(value=payload)
            self._set_status(f"Generating... {payload}/{len(self.timetables)}")

        elif kind == "done_all":
            self.progress.config(value=self.progress["maximum"])
            self._set_busy(False)
            self._set_status(f"Done. Generated timetables for {payload} teacher(s).")
            messagebox.showinfo(
                "Success",
                f"Generated PDF and Excel timetables for {payload} teacher(s).\n\nSaved to:\n{self.output_dir}",
            )

        elif kind == "done_one":
            self.progress.stop()
            self.progress.config(mode="determinate", value=0)
            self._set_busy(False)
            self._set_status(f"Done. Generated timetable for {payload}.")
            messagebox.showinfo(
                "Success",
                f"Generated PDF and Excel timetable for {payload}.\n\nSaved to:\n{self.output_dir}",
            )

        elif kind == "error":
            self.progress.stop()
            self.progress.config(mode="determinate", value=0)
            self._set_busy(False)
            self._set_status("An error occurred.")
            messagebox.showerror("Error", str(payload))
