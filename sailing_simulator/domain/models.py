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
    PERSISTENT_LEFT_WITH_OSCILLATION = "persistent_left_with_oscillation"
    PERSISTENT_RIGHT_WITH_OSCILLATION = "persistent_right_with_oscillation"


class BoatControlMode(str, Enum):
    USER = "user"
    AI = "ai"


class TerrainType(str, Enum):
    HILL = "hill"
    SHORELINE = "shoreline"
    BUILDINGS = "buildings"
    TREES = "trees"
    CLIFF = "cliff"


class RaceEventType(str, Enum):
    BOAT_COLLISION = "boat_collision"
    MARK_COLLISION = "mark_collision"
    FINISH_CROSSED = "finish_crossed"
    MARK_ROUNDED = "mark_rounded"
    START_CROSSED = "start_crossed"
    EARLY_START = "early_start"
    RULE_PENALTY = "rule_penalty"


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
    track: list[Vector2] = field(default_factory=list)
    has_started: bool = False
    is_finished: bool = False
    finish_time_seconds: float | None = None
    mark_approach_target_leg_index: int = -1
    collision_stop_heading: float | None = None
    collision_released_heading: float | None = None
    ai_board: int | None = None
    ai_board_target_leg_index: int = -1
    ai_last_maneuver_seconds: float = -9999.0
    ai_rounding_target_leg_index: int = -1
    ai_rounding_stage: int = 0
    ai_collision_escape_until_seconds: float = 0.0
    ai_collision_escape_heading: float | None = None
    is_early_start: bool = False
    ai_start_strategy: str | None = None
    penalty_turn_remaining_degrees: float = 0.0
    penalty_resume_heading: float | None = None
    penalty_turn_direction: int = 1
    penalty_turns_owed: int = 0
    penalty_clear_position: Vector2 | None = None
    penalties_taken: int = 0
    mark_touch_penalty_target_leg_index: int = -1
    maneuver_remaining_degrees: float = 0.0
    maneuver_turn_direction: int = 1
    maneuver_turn_rate_degrees_per_second: float = 0.0
    maneuver_speed_factor: float = 1.0


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
    persistent_shift_degrees_per_minute: float = 5.0
    gust_percent: float = 0.0


@dataclass
class WindField:
    columns: int = 13
    rows: int = 10
    cell_size: float = 100.0
    cells: list[WindCell] = field(default_factory=list)


@dataclass
class WindCell:
    column: int
    row: int
    center: Vector2
    direction_degrees: float
    speed_knots: float


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
    time_scale: float = 10.0
    start_sequence_seconds: float = 300.0
    events: list[RaceEvent] = field(default_factory=list)
    finished_boats: set[str] = field(default_factory=set)


@dataclass
class RaceEvent:
    event_type: RaceEventType
    message: str
    elapsed_seconds: float


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
        Boat("USER", Vector2(390.0, 790.0), 315.0, control_mode=BoatControlMode.USER),
        Boat("AI 1", Vector2(475.0, 806.0), 315.0),
        Boat("AI 2", Vector2(560.0, 790.0), 315.0),
    ]
    return Scenario(course=course, boats=boats)
