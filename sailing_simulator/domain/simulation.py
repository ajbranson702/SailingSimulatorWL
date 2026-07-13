from __future__ import annotations

import itertools
import math

from sailing_simulator.domain.models import (
    Boat,
    BoatControlMode,
    Mark,
    MarkType,
    Polar,
    RaceEvent,
    RaceEventType,
    Scenario,
    Vector2,
)
from sailing_simulator.domain.race_progress import target_mark_for, total_targets_for

MIN_UPWIND_ANGLE_DEGREES = 45.0
COURSE_UNITS_PER_NAUTICAL_MILE = 1800.0
MAX_TRACK_POINTS = 300
BOAT_COLLISION_RADIUS = 28.0
MARK_COLLISION_RADIUS = 22.0


def step_scenario(scenario: Scenario, elapsed_seconds: float) -> None:
    from sailing_simulator.domain.wind import update_wind_field

    clamp_boats_to_course(scenario)
    previous_positions = {boat.name: boat.position for boat in scenario.boats}
    scenario.race_state.events = []
    scenario.race_state.elapsed_seconds += elapsed_seconds
    update_wind_field(scenario)
    for boat in scenario.boats:
        if boat.control_mode == BoatControlMode.AI:
            continue
        step_boat(boat, scenario, elapsed_seconds)
    detect_race_events(scenario, previous_positions)


def step_boat(boat: Boat, scenario: Scenario, elapsed_seconds: float) -> None:
    from sailing_simulator.domain.wind import wind_at

    if boat.collision_stop_heading is not None:
        if headings_match(boat.heading_degrees, boat.collision_stop_heading):
            boat.speed_knots = 0.0
            append_track_point(boat)
            return
        boat.collision_stop_heading = None

    wind_direction, wind_speed = wind_at(scenario, boat.position)
    target_speed = target_boat_speed(
        scenario.polar,
        wind_speed,
        true_wind_angle(boat.heading_degrees, wind_direction),
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
    clamped_position = clamp_to_course(next_position, scenario.course.boundary_width, scenario.course.boundary_height)
    if clamped_position != next_position:
        boat.speed_knots = 0.0
    boat.position = clamped_position
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
    release_collision_stop_if_heading_changed(boat)


def steer_away_from_wind(boat: Boat, wind_from_degrees: float, degrees: float) -> None:
    difference = signed_angle(wind_from_degrees, boat.heading_degrees)
    turn = -degrees if difference > 0 else degrees
    boat.heading_degrees = normalize_degrees(boat.heading_degrees + turn)
    release_collision_stop_if_heading_changed(boat)


def tack(boat: Boat, wind_from_degrees: float) -> None:
    difference = signed_angle(wind_from_degrees, boat.heading_degrees)
    turn = 90.0 if difference > 0 else -90.0
    boat.heading_degrees = normalize_degrees(boat.heading_degrees + turn)
    boat.speed_knots *= 0.65
    release_collision_stop_if_heading_changed(boat)


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
        boat.collision_stop_heading = None
        boat.collision_released_heading = None
    scenario.race_state.elapsed_seconds = 0.0
    scenario.race_state.events = []
    scenario.race_state.finished_boats = set()


def detect_race_events(scenario: Scenario, previous_positions: dict[str, Vector2]) -> None:
    detect_course_progress(scenario, previous_positions)
    detect_boat_collisions(scenario)
    detect_mark_collisions(scenario)


def detect_course_progress(scenario: Scenario, previous_positions: dict[str, Vector2]) -> None:
    start = scenario.course.start_line
    for boat in scenario.boats:
        if boat.is_finished:
            continue

        previous = previous_positions.get(boat.name)
        if previous is None:
            continue

        segment_position = 0.0
        for _ in range(total_targets_for(scenario.course) + 2):
            if not boat.has_started:
                crossing = segment_intersection_parameter(previous, boat.position, start.pin, start.committee_boat)
                if crossing is None or crossing + 1e-9 < segment_position:
                    break

                boat.has_started = True
                segment_position = crossing
                add_event(scenario, RaceEventType.START_CROSSED, f"{boat.name} started.")
                continue

            target = target_mark_for(scenario.course, boat.target_leg_index)
            if target is not None:
                rounding = mark_crossing_parameter(target.position, previous, boat.position, MARK_COLLISION_RADIUS)
                if rounding is None or rounding + 1e-9 < segment_position:
                    break

                boat.target_leg_index += 1
                segment_position = rounding
                add_event(
                    scenario,
                    RaceEventType.MARK_ROUNDED,
                    f"{boat.name} rounded {target.label}.",
                )
                continue

            crossing = segment_intersection_parameter(previous, boat.position, start.pin, start.committee_boat)
            finish_mark_crossing = finish_mark_crossing_parameter(scenario, previous, boat.position)
            crossing = earliest_valid_parameter([crossing, finish_mark_crossing], segment_position)
            if crossing is None:
                break

            boat.is_finished = True
            boat.finish_time_seconds = scenario.race_state.elapsed_seconds
            scenario.race_state.finished_boats.add(boat.name)
            add_event(
                scenario,
                RaceEventType.FINISH_CROSSED,
                f"{boat.name} finished in {boat.finish_time_seconds:.1f} seconds.",
            )
            break


def detect_start_or_finish_crossings(scenario: Scenario, previous_positions: dict[str, Vector2]) -> None:
    detect_course_progress(scenario, previous_positions)


def detect_mark_roundings(scenario: Scenario, previous_positions: dict[str, Vector2]) -> None:
    for boat in scenario.boats:
        if not boat.has_started or boat.is_finished:
            continue

        target = target_mark_for(scenario.course, boat.target_leg_index)
        if target is None:
            continue

        previous = previous_positions.get(boat.name, boat.position)
        if mark_crossing_parameter(target.position, previous, boat.position, MARK_COLLISION_RADIUS) is not None:
            boat.target_leg_index += 1
            add_event(
                scenario,
                RaceEventType.MARK_ROUNDED,
                f"{boat.name} rounded {target.label}.",
            )


def detect_boat_collisions(scenario: Scenario) -> None:
    colliding_boats: set[str] = set()
    for first, second in itertools.combinations(scenario.boats, 2):
        if distance(first.position, second.position) <= BOAT_COLLISION_RADIUS:
            colliding_boats.add(first.name)
            colliding_boats.add(second.name)
            stop_for_collision(first)
            stop_for_collision(second)
            add_event(
                scenario,
                RaceEventType.BOAT_COLLISION,
                f"{first.name} collided with {second.name}.",
            )

    for boat in scenario.boats:
        if boat.name not in colliding_boats:
            boat.collision_released_heading = None


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


def clamp_boats_to_course(scenario: Scenario) -> None:
    for boat in scenario.boats:
        clamped_position = clamp_to_course(boat.position, scenario.course.boundary_width, scenario.course.boundary_height)
        if clamped_position != boat.position:
            boat.position = clamped_position
            boat.speed_knots = 0.0


def stop_for_collision(boat: Boat) -> None:
    if boat.collision_released_heading is not None and headings_match(boat.heading_degrees, boat.collision_released_heading):
        return

    boat.speed_knots = 0.0
    if boat.collision_stop_heading is None:
        boat.collision_stop_heading = boat.heading_degrees


def release_collision_stop_if_heading_changed(boat: Boat) -> None:
    if boat.collision_stop_heading is not None and not headings_match(boat.heading_degrees, boat.collision_stop_heading):
        boat.collision_stop_heading = None
        boat.collision_released_heading = boat.heading_degrees


def headings_match(first: float, second: float) -> bool:
    return abs(signed_angle(first, second)) < 1e-6


def true_wind_angle(heading_degrees: float, wind_from_degrees: float) -> float:
    return abs(signed_angle(wind_from_degrees, heading_degrees))


def signed_angle(source_degrees: float, target_degrees: float) -> float:
    return math.remainder(source_degrees - target_degrees, 360.0)


def normalize_degrees(degrees: float) -> float:
    return degrees % 360.0


def finish_mark_crossing_parameter(scenario: Scenario, segment_start: Vector2, segment_end: Vector2) -> float | None:
    finish_mark = finish_mark_for(scenario)
    if finish_mark is None:
        return None
    return mark_crossing_parameter(finish_mark.position, segment_start, segment_end, MARK_COLLISION_RADIUS)


def finish_mark_for(scenario: Scenario) -> Mark | None:
    explicit_finish = next((mark for mark in scenario.course.marks if mark.mark_type == MarkType.FINISH), None)
    if explicit_finish is not None:
        return explicit_finish
    return next((mark for mark in scenario.course.marks if mark.mark_type == MarkType.LEEWARD), None)


def earliest_valid_parameter(parameters: list[float | None], minimum: float) -> float | None:
    valid = [parameter for parameter in parameters if parameter is not None and parameter + 1e-9 >= minimum]
    if not valid:
        return None
    return min(valid)


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


def distance_from_segment(point: Vector2, segment_start: Vector2, segment_end: Vector2) -> float:
    crossing = mark_crossing_parameter(point, segment_start, segment_end, float("inf"))
    if crossing is None:
        return distance(point, segment_start)

    closest = point_at_parameter(segment_start, segment_end, crossing)
    return distance(point, closest)


def mark_crossing_parameter(point: Vector2, segment_start: Vector2, segment_end: Vector2, radius: float) -> float | None:
    dx = segment_end.x - segment_start.x
    dy = segment_end.y - segment_start.y
    length_squared = dx * dx + dy * dy
    if length_squared == 0:
        return 0.0 if distance(point, segment_start) <= radius else None

    projection = ((point.x - segment_start.x) * dx + (point.y - segment_start.y) * dy) / length_squared
    projection = max(0.0, min(1.0, projection))
    closest = point_at_parameter(segment_start, segment_end, projection)
    if distance(point, closest) > radius:
        return None
    return projection


def point_at_parameter(segment_start: Vector2, segment_end: Vector2, parameter: float) -> Vector2:
    return Vector2(
        segment_start.x + (segment_end.x - segment_start.x) * parameter,
        segment_start.y + (segment_end.y - segment_start.y) * parameter,
    )


def segment_intersection_parameter(
    first_start: Vector2,
    first_end: Vector2,
    second_start: Vector2,
    second_end: Vector2,
) -> float | None:
    r = Vector2(first_end.x - first_start.x, first_end.y - first_start.y)
    s = Vector2(second_end.x - second_start.x, second_end.y - second_start.y)
    denominator = cross(r, s)
    offset = Vector2(second_start.x - first_start.x, second_start.y - first_start.y)

    if abs(denominator) < 1e-9:
        if abs(cross(offset, r)) >= 1e-9:
            return None

        r_length_squared = r.x * r.x + r.y * r.y
        if r_length_squared == 0:
            return 0.0 if point_on_segment(first_start, second_start, second_end) else None

        first_projection = dot(offset, r) / r_length_squared
        second_offset = Vector2(second_end.x - first_start.x, second_end.y - first_start.y)
        second_projection = dot(second_offset, r) / r_length_squared
        overlap_start = max(0.0, min(first_projection, second_projection))
        overlap_end = min(1.0, max(first_projection, second_projection))
        if overlap_start <= overlap_end:
            return overlap_start
        return None

    t = cross(offset, s) / denominator
    u = cross(offset, r) / denominator
    if -1e-9 <= t <= 1.0 + 1e-9 and -1e-9 <= u <= 1.0 + 1e-9:
        return max(0.0, min(1.0, t))
    return None


def cross(first: Vector2, second: Vector2) -> float:
    return first.x * second.y - first.y * second.x


def dot(first: Vector2, second: Vector2) -> float:
    return first.x * second.x + first.y * second.y


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
