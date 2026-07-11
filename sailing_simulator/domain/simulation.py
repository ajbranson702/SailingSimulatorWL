from __future__ import annotations

import itertools
import math

from sailing_simulator.domain.models import Boat, BoatControlMode, Polar, RaceEvent, RaceEventType, Scenario, Vector2
from sailing_simulator.domain.race_progress import target_mark_for, total_targets_for

MIN_UPWIND_ANGLE_DEGREES = 45.0
COURSE_UNITS_PER_NAUTICAL_MILE = 1800.0
MAX_TRACK_POINTS = 300
BOAT_COLLISION_RADIUS = 28.0
MARK_COLLISION_RADIUS = 22.0


def step_scenario(scenario: Scenario, elapsed_seconds: float) -> None:
    previous_positions = {boat.name: boat.position for boat in scenario.boats}
    scenario.race_state.events = []
    scenario.race_state.elapsed_seconds += elapsed_seconds
    for boat in scenario.boats:
        if boat.control_mode == BoatControlMode.AI:
            continue
        step_boat(boat, scenario, elapsed_seconds)
    detect_race_events(scenario, previous_positions)


def step_boat(boat: Boat, scenario: Scenario, elapsed_seconds: float) -> None:
    target_speed = target_boat_speed(
        scenario.polar,
        scenario.wind_model.base_speed_knots,
        true_wind_angle(boat.heading_degrees, scenario.wind_model.base_direction_degrees),
    )
    acceleration = 1.3
    speed_delta = target_speed - boat.speed_knots
    max_delta = acceleration * elapsed_seconds
    boat.speed_knots += max(-max_delta, min(max_delta, speed_delta))

    distance_nm = boat.speed_knots * elapsed_seconds / 3600.0
    distance_units = distance_nm * COURSE_UNITS_PER_NAUTICAL_MILE
    radians = math.radians(boat.heading_degrees)
    next_position = Vector2(
        boat.position.x + math.sin(radians) * distance_units,
        boat.position.y - math.cos(radians) * distance_units,
    )
    boat.position = clamp_to_course(next_position, scenario.course.boundary_width, scenario.course.boundary_height)
    append_track_point(boat)


def target_boat_speed(polar: Polar, true_wind_speed: float, true_wind_angle_degrees: float) -> float:
    polar_speed = interpolated_polar_speed(polar, true_wind_speed, true_wind_angle_degrees)
    if true_wind_angle_degrees >= MIN_UPWIND_ANGLE_DEGREES:
        return polar_speed

    return polar_speed * max(0.0, true_wind_angle_degrees / MIN_UPWIND_ANGLE_DEGREES)


def interpolated_polar_speed(polar: Polar, true_wind_speed: float, true_wind_angle_degrees: float) -> float:
    wind_speeds = sorted(polar.speeds_by_tws_and_twa)
    lower_tws, upper_tws = bounds_for(wind_speeds, true_wind_speed)
    lower_speed = speed_for_wind_row(polar.speeds_by_tws_and_twa[lower_tws], true_wind_angle_degrees)
    upper_speed = speed_for_wind_row(polar.speeds_by_tws_and_twa[upper_tws], true_wind_angle_degrees)
    return interpolate(lower_tws, lower_speed, upper_tws, upper_speed, true_wind_speed)


def speed_for_wind_row(row: dict[float, float], true_wind_angle_degrees: float) -> float:
    angles = sorted(row)
    lower_angle, upper_angle = bounds_for(angles, true_wind_angle_degrees)
    return interpolate(lower_angle, row[lower_angle], upper_angle, row[upper_angle], true_wind_angle_degrees)


def steer_toward_wind(boat: Boat, wind_from_degrees: float, degrees: float) -> None:
    difference = signed_angle(wind_from_degrees, boat.heading_degrees)
    turn = degrees if difference > 0 else -degrees
    boat.heading_degrees = normalize_degrees(boat.heading_degrees + turn)


def steer_away_from_wind(boat: Boat, wind_from_degrees: float, degrees: float) -> None:
    difference = signed_angle(wind_from_degrees, boat.heading_degrees)
    turn = -degrees if difference > 0 else degrees
    boat.heading_degrees = normalize_degrees(boat.heading_degrees + turn)


def tack(boat: Boat, wind_from_degrees: float) -> None:
    difference = signed_angle(wind_from_degrees, boat.heading_degrees)
    turn = 90.0 if difference > 0 else -90.0
    boat.heading_degrees = normalize_degrees(boat.heading_degrees + turn)
    boat.speed_knots *= 0.65


def reset_boats_to_start(scenario: Scenario) -> None:
    base_x = min(scenario.course.start_line.pin.x, scenario.course.start_line.committee_boat.x) + 60.0
    base_y = max(scenario.course.start_line.pin.y, scenario.course.start_line.committee_boat.y) + 35.0
    for index, boat in enumerate(scenario.boats):
        boat.position = Vector2(base_x + index * 42.0, base_y + (index % 2) * 16.0)
        boat.heading_degrees = 315.0
        boat.speed_knots = 0.0
        boat.track = []
        boat.target_leg_index = 0
        boat.has_started = False
        boat.is_finished = False
        boat.finish_time_seconds = None
    scenario.race_state.elapsed_seconds = 0.0
    scenario.race_state.events = []
    scenario.race_state.finished_boats = set()


def detect_race_events(scenario: Scenario, previous_positions: dict[str, Vector2]) -> None:
    detect_start_or_finish_crossings(scenario, previous_positions)
    detect_mark_roundings(scenario)
    detect_boat_collisions(scenario)
    detect_mark_collisions(scenario)


def detect_start_or_finish_crossings(scenario: Scenario, previous_positions: dict[str, Vector2]) -> None:
    start = scenario.course.start_line
    for boat in scenario.boats:
        if boat.is_finished:
            continue

        previous = previous_positions.get(boat.name)
        if previous is None or previous == boat.position:
            continue

        if segments_intersect(previous, boat.position, start.pin, start.committee_boat):
            if not boat.has_started:
                boat.has_started = True
                add_event(scenario, RaceEventType.START_CROSSED, f"{boat.name} started.")
            elif boat.target_leg_index >= total_targets_for(scenario.course):
                boat.is_finished = True
                boat.finish_time_seconds = scenario.race_state.elapsed_seconds
                scenario.race_state.finished_boats.add(boat.name)
                add_event(
                    scenario,
                    RaceEventType.FINISH_CROSSED,
                    f"{boat.name} finished in {boat.finish_time_seconds:.1f} seconds.",
                )


def detect_mark_roundings(scenario: Scenario) -> None:
    for boat in scenario.boats:
        if not boat.has_started or boat.is_finished:
            continue

        target = target_mark_for(scenario.course, boat.target_leg_index)
        if target is None:
            continue

        if distance(boat.position, target.position) <= MARK_COLLISION_RADIUS:
            boat.target_leg_index += 1
            add_event(
                scenario,
                RaceEventType.MARK_ROUNDED,
                f"{boat.name} rounded {target.label}.",
            )


def detect_boat_collisions(scenario: Scenario) -> None:
    for first, second in itertools.combinations(scenario.boats, 2):
        if distance(first.position, second.position) <= BOAT_COLLISION_RADIUS:
            add_event(
                scenario,
                RaceEventType.BOAT_COLLISION,
                f"{first.name} collided with {second.name}.",
            )


def detect_mark_collisions(scenario: Scenario) -> None:
    for boat in scenario.boats:
        for mark in scenario.course.marks:
            if distance(boat.position, mark.position) <= MARK_COLLISION_RADIUS:
                add_event(
                    scenario,
                    RaceEventType.MARK_COLLISION,
                    f"{boat.name} hit mark {mark.label}.",
                )


def add_event(scenario: Scenario, event_type: RaceEventType, message: str) -> None:
    scenario.race_state.events.append(
        RaceEvent(
            event_type=event_type,
            message=message,
            elapsed_seconds=scenario.race_state.elapsed_seconds,
        )
    )


def true_wind_angle(heading_degrees: float, wind_from_degrees: float) -> float:
    return abs(signed_angle(wind_from_degrees, heading_degrees))


def signed_angle(source_degrees: float, target_degrees: float) -> float:
    return math.remainder(source_degrees - target_degrees, 360.0)


def normalize_degrees(degrees: float) -> float:
    return degrees % 360.0


def bounds_for(values: list[float], target: float) -> tuple[float, float]:
    if target <= values[0]:
        return values[0], values[0]
    if target >= values[-1]:
        return values[-1], values[-1]

    for lower, upper in zip(values, values[1:]):
        if lower <= target <= upper:
            return lower, upper

    return values[-1], values[-1]


def interpolate(lower_x: float, lower_y: float, upper_x: float, upper_y: float, target_x: float) -> float:
    if lower_x == upper_x:
        return lower_y
    ratio = (target_x - lower_x) / (upper_x - lower_x)
    return lower_y + ratio * (upper_y - lower_y)


def clamp_to_course(position: Vector2, width: float, height: float) -> Vector2:
    return Vector2(max(0.0, min(width, position.x)), max(0.0, min(height, position.y)))


def distance(first: Vector2, second: Vector2) -> float:
    return math.hypot(first.x - second.x, first.y - second.y)


def segments_intersect(first_start: Vector2, first_end: Vector2, second_start: Vector2, second_end: Vector2) -> bool:
    first_direction = orientation(first_start, first_end, second_start)
    second_direction = orientation(first_start, first_end, second_end)
    third_direction = orientation(second_start, second_end, first_start)
    fourth_direction = orientation(second_start, second_end, first_end)

    if first_direction == 0 and point_on_segment(second_start, first_start, first_end):
        return True
    if second_direction == 0 and point_on_segment(second_end, first_start, first_end):
        return True
    if third_direction == 0 and point_on_segment(first_start, second_start, second_end):
        return True
    if fourth_direction == 0 and point_on_segment(first_end, second_start, second_end):
        return True

    return first_direction != second_direction and third_direction != fourth_direction


def orientation(first: Vector2, second: Vector2, third: Vector2) -> int:
    value = (second.y - first.y) * (third.x - second.x) - (second.x - first.x) * (third.y - second.y)
    if abs(value) < 1e-9:
        return 0
    return 1 if value > 0 else 2


def point_on_segment(point: Vector2, segment_start: Vector2, segment_end: Vector2) -> bool:
    return (
        min(segment_start.x, segment_end.x) <= point.x <= max(segment_start.x, segment_end.x)
        and min(segment_start.y, segment_end.y) <= point.y <= max(segment_start.y, segment_end.y)
    )


def append_track_point(boat: Boat) -> None:
    if boat.track and math.hypot(boat.position.x - boat.track[-1].x, boat.position.y - boat.track[-1].y) < 1.0:
        return

    boat.track.append(boat.position)
    if len(boat.track) > MAX_TRACK_POINTS:
        del boat.track[: len(boat.track) - MAX_TRACK_POINTS]
