# Sailing Race Simulator

Windows desktop simulator for experimenting with windward-leeward sailing race scenarios.

## Current Status

Phase 5 is underway:

- PySide6 app shell
- Single simulator screen
- Draggable course marks and start-line endpoints
- Scenario controls panel
- Initial domain data model
- Course presets for W2, T3, W4, and W6
- Scenario save/load JSON support
- User boat movement under static wind
- Default polar lookup with no-go-zone slowdown
- Keyboard steering and tack controls
- Adjustable simulation speed
- Boat track rendering
- Basic finish-line and collision event detection
- Course leg progress with mark rounding and gated finish detection
- Wind grid generated from current wind scenario
- Static, oscillating, persistent-shift, combined-shift, and gusty wind modes
- Boat physics and sail display use local wind
- Basic domain tests

## Controls

- Up arrow: head up toward the wind
- Down arrow: bear away from the wind
- `T`: tack
- Start/Pause/Reset: control simulation playback
- Sim speed: run the simulation from 1x to 50x real time

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
