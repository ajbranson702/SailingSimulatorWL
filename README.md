# Sailing Race Simulator

Windows desktop simulator for experimenting with windward-leeward sailing race scenarios.

## Current Status

Phase 1 is underway:

- PySide6 app shell
- Single simulator screen
- Course canvas placeholder
- Scenario controls panel
- Initial domain data model
- Basic domain tests

## Environment

Use the project-local `.venv` environment:

```text
C:\Users\ajbra\PycharmProjects\SailingRaceSimulator\.venv\Scripts\python.exe
```

From PowerShell:

```powershell
.\.venv\Scripts\python.exe main.py
```

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests
```

## Qt Smoke Test

This creates the main window offscreen without opening a visible app window:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
.\.venv\Scripts\python.exe -c "from PySide6.QtWidgets import QApplication; from sailing_simulator.ui.main_window import MainWindow; app = QApplication([]); window = MainWindow(); assert window.windowTitle() == 'Sailing Race Simulator'; assert window.centralWidget() is not None"
```
