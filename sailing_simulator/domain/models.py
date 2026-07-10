from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


@dataclass(frozen=True)
class Vector2:
    x: float
    y: float


class MarkType(str, Enum):
    WINDWARD = "windward"
    LEEWARD = "leeward"
    GYBE = "gybe"
    FINISH = "finish"


class RaceFormat(str, Enum):
    W2 = "W2"
    T3 = "T3"
    W4 = "W4"
    W6 = "W6"


class WindMode(str, Enum):
    STATIC = "static"
    OSCILLATING = "oscillating"
    PERSISTENT_LEFT = "persistent_left"
    PERSISTENT_RIGHT = "persistent_right"
    PERSISTENT_WITH_OSCILLATION = "persistent_with_oscillation"


class BoatControlMode(str, Enum):
    USER = "user"
    AI = "ai"


class TerrainType(str, Enum):
    HILL = "hill"
    SHORELINE = "shoreline"
    BUILDINGS = "buildings"
    TREES = "trees"
    CLIFF = "cliff"


@dataclass
class StartLine:
    pin: Vector2 = field(default_factory=lambda: Vector2(360.0, 700.0))
    committee_boat: Vector2 = field(default_factory=lambda: Vector2(560.0, 700.0))


@dataclass
class Mark:
    mark_type: MarkType
    position: Vector2
    label: str


@dataclass
class Course:
    race_format: RaceFormat = RaceFormat.W2
    start_line: StartLine = field(default_factory=StartLine)
    marks: list[Mark] = field(default_factory=list)
    boundary_width: float = 900.0
    boundary_height: float = 900.0


@dataclass
class Boat:
    name: str
    position: Vector2
    heading_degrees: float
    speed_knots: float = 0.0
    control_mode: BoatControlMode = BoatControlMode.AI
    target_leg_index: int = 0


@dataclass
class Polar:
    name: str = "Default Training Boat"
    speeds_by_tws_and_twa: dict[float, dict[float, float]] = field(
        default_factory=lambda: {
            6.0: {45.0: 3.2, 60.0: 4.1, 90.0: 4.5, 120.0: 4.2, 150.0: 3.4, 180.0: 2.6},
            10.0: {45.0: 5.0, 60.0: 6.1, 90.0: 6.5, 120.0: 6.2, 150.0: 5.1, 180.0: 4.0},
            16.0: {45.0: 6.2, 60.0: 7.5, 90.0: 8.1, 120.0: 8.4, 150.0: 7.2, 180.0: 5.8},
        }
    )


@dataclass
class WindModel:
    mode: WindMode = WindMode.STATIC
    base_direction_degrees: float = 0.0
    base_speed_knots: float = 10.0
    oscillation_amplitude_degrees: float = 10.0
    oscillation_period_seconds: float = 180.0
    persistent_shift_degrees_per_minute: float = 0.0
    gust_percent: float = 0.0


@dataclass
class WindField:
    columns: int = 9
    rows: int = 9
    cell_size: float = 100.0


@dataclass
class TerrainObject:
    terrain_type: TerrainType
    position: Vector2
    height: float
    influence_radius: float


@dataclass
class RaceState:
    elapsed_seconds: float = 0.0
    is_running: bool = False


@dataclass
class Scenario:
    course: Course = field(default_factory=Course)
    boats: list[Boat] = field(default_factory=list)
    wind_model: WindModel = field(default_factory=WindModel)
    wind_field: WindField = field(default_factory=WindField)
    polar: Polar = field(default_factory=Polar)
    terrain: list[TerrainObject] = field(default_factory=list)
    race_state: RaceState = field(default_factory=RaceState)


def default_scenario() -> Scenario:
    from sailing_simulator.domain.presets import course_for_format

    course = course_for_format(RaceFormat.W2)
    boats = [
        Boat("USER", Vector2(420.0, 735.0), 315.0, control_mode=BoatControlMode.USER),
        Boat("AI 1", Vector2(465.0, 745.0), 315.0),
        Boat("AI 2", Vector2(510.0, 735.0), 315.0),
    ]
    return Scenario(course=course, boats=boats)
