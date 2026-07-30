Build a Python desktop application called "Teacher Timetable Generator".

Goal:
The uploaded Excel workbook is the ONLY source of truth.

Requirements:

- Read every worksheet.
- Each worksheet represents one Level.
- Row containing "TIME/DAY" holds the time slots.
- First column contains weekdays.
- Every lesson cell contains "Subject - Teacher" (examples: "EET- Mr. Mathias", "TD-Mr. Marobo", "CA&CAD Mr. Mbelwa").

The program must:

1. Parse every sheet automatically.
2. Ignore empty cells, PARADE and TEA BREAK.
3. Extract:
   - Level
   - Day
   - Time
   - Subject
   - Teacher
4. Group lessons by teacher.
5. Generate a clean timetable for every teacher.
6. Export:
   - PDF
   - Excel (.xlsx)
7. Save output as:

Output/
    PDFs/
        Mr Mathias.pdf
        Mr Marobo.pdf
    Excel/
        Mr Mathias.xlsx
        Mr Marobo.xlsx

Desktop UI (Tkinter or CustomTkinter):

- Select Master Excel
- Generate All
- Generate One Teacher
- Search Teacher
- Open Output Folder
- Progress Bar
- Success/Error messages

Architecture:

reader.py
parser.py
teacher_generator.py
pdf_export.py
excel_export.py
gui.py
main.py

Rules:

- Never modify the master workbook.
- Master workbook is always the source of truth.
- Regenerating must overwrite old teacher files.
- Code must be modular, typed, documented and production-ready.
- Handle merged cells and multiple worksheets.
- Auto-detect levels and teachers without hardcoding names.