# Packaging

Builds a standalone Windows `.exe` and a `.msi` installer for
Teacher Timetable Generator. End users need neither Python nor any
dependencies installed.

## 1. Build the standalone exe (PyInstaller)

```
pip install pyinstaller
python -m PyInstaller packaging\TeacherTimetableGenerator.spec --distpath packaging\dist --workpath packaging\build --noconfirm
```

Produces `packaging\dist\TeacherTimetableGenerator.exe`.

## 2. Build the MSI installer (WiX Toolset v7)

```
dotnet tool install --global wix
wix eula accept wix7
wix extension add WixToolset.UI.wixext -g
wix build packaging\wix\Product.wxs -arch x64 -ext WixToolset.UI.wixext -o packaging\dist\TeacherTimetableGenerator.msi
```

`packaging\wix\Product.wxs` must be built from the project root (source
paths inside it are relative to the invocation directory). It installs to
`Program Files\Teacher Timetable Generator`, adds a Start Menu shortcut, and
registers with Add/Remove Programs for a clean uninstall.

Notes:
- WiX v7 requires accepting its Open Source Maintenance Fee EULA once per
  machine (`wix eula accept wix7`) before it will build. This is free to use;
  it only asks organizations with >$10k/year revenue to sponsor the project.
- Bump `Version` in `Product.wxs` (and `packaging\version_info.txt`) for
  each release; `MajorUpgrade` handles upgrading an existing install in
  place.
