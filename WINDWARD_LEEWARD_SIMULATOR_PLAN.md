# Windward-Leeward Sailing Race Simulator Plan

## Purpose

Build a Windows desktop app for experimenting with windward-leeward sailing race scenarios. The app should let a user lay out a race course, define wind behavior, control one boat, and race against computer-controlled boats while visualizing wind changes across the course.

The first goal is not a full tactical racing game. It is a practical simulator for learning how boats, wind shifts, gusts, and course geometry interact.

## Product Goals

- Show a single birdseye course view with wind conventionally coming from the top of the screen.
- Let the user quickly create and adjust windward-leeward courses.
- Simulate realistic enough boat motion for tactical experimentation.
- Make wind visible and understandable through a grid of arrows across the course.
- Allow repeatable scenarios by saving/loading course, fleet, wind, and boat-polar settings.
- Keep controls simple enough for live experimentation.

## Recommended Initial Stack

- Language: Python
- Desktop UI: PySide6 / Qt for Windows
- Rendering: Qt `QGraphicsView` or a custom `QWidget` canvas for the 2D course
- Data files: JSON for scenarios and CSV/JSON for boat polars
- Testing: `pytest` for simulation logic, with manual UI smoke tests early on

This fits the current Python starter project and keeps packaging for Windows achievable with tools such as PyInstaller later.

## Core Screen

The app should open directly into the simulator screen.

Main areas:

- Course canvas: top-down course, marks, boats, tracks, and wind grid.
- Scenario controls: course setup, fleet size, number of legs, wind model, wind strength, gust settings, and terrain tools.
- Boat/race status: selected boat heading, speed, tack/gybe state, leg progress, elapsed time, and current wind at boat location.
- Playback controls: start, pause, reset, simulation speed, and optionally step-forward.

Wind display convention:

- The top of the screen is the nominal upwind direction.
- Wind arrows should show the local wind direction and relative wind strength at grid points.
- A wind direction of 0 degrees means wind comes from the top of the screen and blows downward.

## Course Features

Required course objects:

- Start line
- Windward mark
- Leeward mark or finish line
- Optional gybe/spreader mark

Course setup behavior:

- User can place and drag course objects on the canvas.
- Start line has two draggable ends.
- Marks have labels and selectable positions.
- The course should validate that required marks exist before race start.
- The race course should support common formats:
  - `W2`: start, windward mark, downwind finish
  - `T3`: start, windward mark, gybe mark, downwind finish
  - `W4`: start, windward mark, leeward mark, windward mark, downwind finish
  - `W6`: two `W3` laps, then downwind finish
  - Future: custom leg sequences and offset/spreader mark routes

## Fleet Features

- User specifies number of boats.
- One boat is user-controlled.
- Remaining boats are computer-controlled.
- Boats start on or behind the start line.
- Boats should have simple collision/rule handling eventually, but the first version can focus on movement and tactics.

Initial AI behavior:

- Sail toward the next mark using simple VMG-based decisions.
- Tack or gybe when the current board becomes inefficient or when reaching a course boundary.
- Prefer routes that improve VMG toward the next mark under the current wind.

Later AI behavior:

- React to oscillating shifts.
- Avoid other boats.
- Cover or split from competitors.
- Choose lanes based on gusts, terrain effects, and laylines.

## User Boat Controls

Keyboard controls:

- Up arrow: head up toward the wind when sailing upwind, or steer toward a hotter angle when sailing downwind.
- Down arrow: bear away from the wind when sailing upwind, or steer deeper when sailing downwind.
- `T`: tack, turning approximately 90 degrees onto the opposite tack.

Future controls:

- `G`: gybe when sailing downwind.
- Space: pause/resume.
- `R`: reset scenario.
- Mouse selection for choosing controlled boat or inspecting wind cells.

Sailing constraints:

- Boat cannot sail efficiently closer than 45 degrees to the true wind.
- If the true wind angle is less than 45 degrees, boat speed should degrade sharply.
- If pointed directly into the wind, the boat should slow toward zero and may drift.

## Boat Performance Model

The app needs a polar table or polar diagram so boat speed can be calculated from:

- True wind speed
- True wind angle

Initial implementation:

- Load a CSV or JSON polar table.
- Interpolate between known wind speeds and angles.
- Provide one built-in default polar so the simulator works without external files.

Example polar table shape:

| True Wind Speed | 45 deg | 60 deg | 90 deg | 120 deg | 150 deg | 180 deg |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 6 kt | 3.2 | 4.1 | 4.5 | 4.2 | 3.4 | 2.6 |
| 10 kt | 5.0 | 6.1 | 6.5 | 6.2 | 5.1 | 4.0 |
| 16 kt | 6.2 | 7.5 | 8.1 | 8.4 | 7.2 | 5.8 |

## Wind Scenario Model

Wind settings:

- Base wind direction
- Base wind strength
- Static wind mode
- Oscillating wind mode
- Continuous left shift
- Continuous right shift
- Continuous shift with oscillation
- Gust percentage relative to base wind
- Gust frequency and gust cell size

Initial wind modes:

- Static: direction and strength stay fixed.
- Oscillating: direction moves left/right over time using amplitude and period.
- Persistent shift: direction trends steadily left or right over time.
- Persistent plus oscillating: trend plus periodic oscillation.
- Gusty: strength varies by time and location as a percentage of base wind.

Wind field:

- The course should maintain a grid of wind cells.
- Each cell stores local direction and speed.
- Boat physics queries the wind field at the boat position.
- Wind arrows on the canvas render each cell's direction and relative strength.

## Terrain Wind Effects

Terrain is an advanced feature and should be introduced after the core sailing and wind engine work.

Terrain object properties:

- Position and shape
- Height
- Terrain type, such as hill, shoreline, buildings, trees, or cliffs
- Wind shadow strength
- Deflection strength
- Turbulence level

Expected effects:

- Tall terrain creates a wind shadow downwind.
- Terrain can bend wind around edges.
- Terrain can create turbulent gust/lull zones.
- Effects should be visualized in the wind-arrow grid.

Initial terrain model:

- Use simple geometric influence zones.
- Reduce wind strength behind terrain.
- Deflect wind direction around the sides.
- Add turbulence noise inside affected cells.

Later terrain model:

- More physically plausible flow fields.
- Layered terrain effects from multiple objects.
- Presets for common sailing venues.

## Data Model

Suggested core entities:

- `Scenario`: course, boats, wind model, terrain, race settings
- `Course`: start line, marks, leg sequence, boundaries
- `Mark`: position, type, label
- `Boat`: position, heading, speed, tack, target leg, control mode
- `Polar`: speed lookup by true wind speed and true wind angle
- `WindModel`: global wind settings plus time-based changes
- `WindField`: grid of local wind vectors
- `TerrainObject`: shape, height, type, wind influence parameters
- `RaceState`: elapsed time, status, rankings, leg completion

## Simulation Loop

Recommended first simulation step:

1. Read user input.
2. Update global wind scenario for current simulation time.
3. Update wind grid, including gusts and terrain effects.
4. For each boat, query local wind at boat position.
5. Calculate true wind angle from boat heading and local wind direction.
6. Lookup boat target speed from polar table.
7. Apply acceleration, slowing, and no-go-zone penalties.
8. Move boats.
9. Check mark roundings, leg completion, and finish.
10. Render course, boats, tracks, and wind arrows.

## MVP Scope

The first useful version should include:

- Single Windows desktop screen.
- Course canvas with draggable start line, windward mark, and leeward/finish mark.
- Boat count setting.
- One user boat and simple AI boats.
- `W2`, `T3`, `W4`, and `W6` course formats.
- Static and oscillating wind.
- Base wind strength.
- Wind arrow grid.
- Keyboard steering and tack command.
- Built-in default polar table.
- Basic race start, pause, reset, and elapsed-time display.

Out of MVP:

- Terrain wind effects.
- Sophisticated tactical AI.
- Collision avoidance and racing rules.
- Multiplayer.
- Advanced weather import.
- High-fidelity hydrodynamics.

## Phase-Based Build Plan

The build should be organized around phases rather than fixed calendar weeks. That keeps the plan useful whether development moves faster, slower, or pauses between sessions. Each phase has a concrete deliverable and can be treated as complete when its exit criteria are met.

| Phase | Focus | Exit Criteria |
| --- | --- | --- |
| 1 | Product skeleton and technical foundation | App launches to the simulator screen |
| 2 | Course editor | User can lay out and reload a course |
| 3 | Boat motion and user controls | User can sail under static wind |
| 4 | Race state and course progress | User can complete a solo W2/W4 race |
| 5 | Wind engine and visualization | User can experiment with changing wind |
| 6 | Computer-controlled boats | User can race against AI boats |
| 7 | Terrain wind effects | Terrain affects the visible wind grid |
| 8 | Polish, packaging, and scenario library | Packaged Windows prototype is ready to use |

### Phase 1: Product Skeleton and Technical Foundation

- Replace the starter script with a basic PySide6 app shell.
- Create the main window and single simulator screen layout.
- Add an empty course canvas and side control panel.
- Define initial data classes for scenario, course, mark, boat, wind, and polar.
- Add project structure and first tests for pure simulation helpers.

Deliverable: app launches on Windows and displays an empty simulator screen.

### Phase 2: Course Editor

- Draw start line and marks.
- Allow dragging start line endpoints and marks.
- Add course presets for `W2`, `T3`, `W4`, and `W6`.
- Validate required course objects.
- Save/load a basic scenario JSON file.

Deliverable: user can lay out a windward-leeward course and reload it.

### Phase 3: Boat Motion and User Controls

- Add one user-controlled boat.
- Implement keyboard steering and tack command.
- Add built-in polar table and interpolation.
- Implement no-go-zone slowdown inside 45 degrees.
- Draw boat heading, wake/track, speed, and status.

Deliverable: user can sail a boat around the course under static wind.

Status: initial implementation complete.

### Phase 4: Race State and Course Progress

- Add race start, pause, reset, and simulation speed controls.
- Implement leg sequencing for `W2`, `T3`, `W4`, and `W6`.
- Detect mark rounding and finish crossing.
- Detect basic boat, mark, and finish-line events.
- Show elapsed time and current leg.
- Add basic boundary handling.

Deliverable: user can complete a simple windward-leeward race alone.

Status: initial race-progress implementation complete.

### Phase 5: Wind Engine and Visualization

- Implement wind grid cells.
- Render arrows across the course.
- Add static, oscillating, persistent shift, and combined shift modes.
- Add base wind strength and gust percentage settings.
- Show local wind at the selected/user boat.

Deliverable: user can experiment with changing wind and see it on the course.

Status: initial wind engine and visualization implementation complete.

### Phase 6: Computer-Controlled Boats

- Add fleet-size setting.
- Spawn AI boats at the start.
- Implement simple VMG-based steering to next mark.
- Add tack/gybe decisions.
- Show rankings and boat identifiers.

Deliverable: user can race against computer-controlled boats.

### Phase 7: Terrain Wind Effects

- Add terrain drawing/placement tools.
- Add terrain height and type controls.
- Implement wind shadow, deflection, and turbulence zones.
- Blend terrain effects into the wind grid.
- Add visual indication of affected wind cells.

Deliverable: user can add terrain and see it alter wind behavior.

### Phase 8: Polish, Packaging, and Scenario Library

- Improve UI layout and visual clarity.
- Add default scenarios.
- Add polar import/export.
- Add scenario save/load polish.
- Package app for Windows.
- Run end-to-end manual test scenarios.

Deliverable: packaged Windows prototype ready for repeated experimentation.

## Suggested Milestones

- Milestone 1: Course layout prototype, after Phase 2.
- Milestone 2: Sailable single-boat simulator, after Phase 4.
- Milestone 3: Wind scenario lab, after Phase 5.
- Milestone 4: Race against AI boats, after Phase 6.
- Milestone 5: Terrain-aware prototype, after Phase 8.

## Early Design Decisions To Confirm

- Should this be a pure Windows desktop app, or should it eventually become web-based too?
- What boat type should the default polar represent?
- Should the windward mark always be near the top of the screen, or can courses be rotated while wind remains visually top-down?
- Should `T` always tack 90 degrees, or should it switch to the mirrored true wind angle from the previous tack?
- Should gybing be automatic downwind at first, or controlled separately with `G`?
- Should AI boats prioritize simple mark navigation or realistic tactical choices early?

## Immediate Next Steps

1. Confirm the initial technology stack.
2. Choose the default boat/polar source.
3. Decide whether terrain is needed in the first playable prototype or can remain a later-phase feature.
4. Create the app project structure.
5. Build the Phase 1 PySide6 app shell.
