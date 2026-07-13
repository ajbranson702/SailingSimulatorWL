from __future__ import annotations

import itertools
import math
import random

from sailing_simulator.domain.models import (
    Boat,
    BoatControlMode,
    Mark,
    MarkType,
    Polar,
    RaceEvent,
    RaceEventType,
    RaceFormat,
    Scenario,
    Vector2,
)
from sailing_simulator.domain.race_progress import finish_position_for, target_mark_for, total_targets_for

MIN_UPWIND_ANGLE_DEGREES = 45.0
COURSE_UNITS_PER_NAUTICAL_MILE = 1800.0
MAX_TRACK_POINTS = 300
BOAT_COLLISION_RADIUS = 28.0
MARK_COLLISION_RADIUS = 22.0
START_FINISH_LINE_EXTENSION = 45.0
START_FINISH_LINE_TOUCH_RADIUS = 18.0
MARK_ROUNDING_GATE_HALF_WIDTH = 140.0
MARK_ROUNDING_ADVANCE_DISTANCE = 4.0
MARK_ROUNDING_COMPLETION_MAX_ADVANCE = 70.0
AI_MARK_ROUNDING_OFFSET = 112.0
AI_MARK_APPROACH_DISTANCE = 95.0
AI_MARK_EXIT_DISTANCE = 65.0
AI_MARK_SWITCH_DISTANCE = 35.0
AI_LEEWARD_ROUNDING_OFFSET = 135.0
AI_LEEWARD_ROUNDING_ADVANCE = 92.0
AI_CLOSE_TARGET_RADIUS = 85.0
AI_BOUNDARY_MARGIN = 75.0
AI_MARK_AVOIDANCE_LOOKAHEAD = 140.0
AI_MARK_AVOIDANCE_RADIUS = 42.0
AI_MIN_MANEUVER_INTERVAL_SECONDS = 18.0
AI_COLLISION_ESCAPE_MIN_SECONDS = 10.0
AI_COLLISION_ESCAPE_MAX_SECONDS = 28.0
AI_UPWIND_ANGLE = 45.0
AI_DOWNWIND_ANGLE = 35.0


def step_scenario(scenario: Scenario, elapsed_seconds: float) -> None:
    from sailing_simulator.domain.wind import update_wind_field

    clamp_boats_to_course(scenario)
    previous_positions = {boat.name: boat.position for boat in scenario.boats}
    scenario.race_state.events = []
    scenario.race_state.elapsed_seconds += elapsed_seconds
    update_wind_field(scenario)
    for boat in scenario.boats:
        if boat.control_mode == BoatControlMode.AI:
            update_ai_heading(boat, scenario)
        step_boat(boat, scenario, elapsed_seconds)
    detect_race_events(scenario, previous_positions)


def update_ai_heading(boat: Boat, scenario: Scenario) -> None:
    from sailing_simulator.domain.wind import wind_at

    if boat.is_finished:
        boat.speed_knots = 0.0
        return

    if boat.ai_collision_escape_heading is not None:
        if scenario.race_state.elapsed_seconds < boat.ai_collision_escape_until_seconds:
            boat.heading_degrees = turn_toward_heading(boat.heading_degrees, boat.ai_collision_escape_heading, 30.0)
            release_collision_stop_if_heading_changed(boat)
            return
        boat.ai_collision_escape_heading = None

    target_position = ai_target_position(boat, scenario)
    wind_direction, wind_speed = wind_at(scenario, boat.position)
    leg_mode = ai_leg_mode(wind_direction, bearing_to(boat.position, target_position))
    reset_ai_board_if_needed(boat, scenario, target_position, leg_mode, wind_direction, wind_speed)
    if boat.collision_stop_heading is not None:
        boat.ai_board = -boat.ai_board if boat.ai_board is not None else best_ai_board(
            boat,
            scenario,
            target_position,
            leg_mode,
            wind_direction,
            wind_speed,
        )
        boat.ai_last_maneuver_seconds = scenario.race_state.elapsed_seconds

    steering_target = ai_steering_target_position(boat, scenario)
    if boat.collision_stop_heading is None and distance(boat.position, target_position) <= AI_CLOSE_TARGET_RADIUS:
        desired_heading = best_vmg_heading(boat, scenario, steering_target)
        boat.heading_degrees = turn_toward_heading(boat.heading_degrees, desired_heading, 18.0)
        release_collision_stop_if_heading_changed(boat)
        return

    if should_change_ai_board(boat, scenario, target_position, leg_mode, wind_direction, wind_speed):
        boat.ai_board = -boat.ai_board if boat.ai_board is not None else best_ai_board(
            boat,
            scenario,
            target_position,
            leg_mode,
            wind_direction,
            wind_speed,
        )
        boat.ai_last_maneuver_seconds = scenario.race_state.elapsed_seconds

    desired_heading = ai_board_heading(wind_direction, leg_mode, boat.ai_board or 1)
    boat.heading_degrees = turn_toward_heading(boat.heading_degrees, desired_heading, 18.0)
    release_collision_stop_if_heading_changed(boat)


def first_ai_target_position(scenario: Scenario) -> Vector2:
    first_mark = target_mark_for(scenario.course, 0)
    if first_mark is not None:
        return first_mark.position
    return ai_finish_target_position(scenario)


def ai_target_position(boat: Boat, scenario: Scenario) -> Vector2:
    if not boat.has_started:
        return first_ai_target_position(scenario)

    target = target_mark_for(scenario.course, boat.target_leg_index)
    if target is not None:
        return target.position
    return ai_finish_target_position_for_boat(boat, scenario)


def ai_steering_target_position(boat: Boat, scenario: Scenario) -> Vector2:
    if not boat.has_started:
        target = target_mark_for(scenario.course, 0)
        target_index = 0
    else:
        target = target_mark_for(scenario.course, boat.target_leg_index)
        target_index = boat.target_leg_index

    if target is None:
        return ai_finish_target_position_for_boat(boat, scenario)

    incoming_unit = incoming_leg_unit_for(scenario, target_index)
    gate_unit = mark_rounding_gate_unit_for(scenario, target_index)
    if incoming_unit is None or gate_unit is None:
        return target.position

    incoming_unit = incoming_leg_unit_for(scenario, target_index)
    exit_side = rounding_boat_side_unit(scenario, target_index)
    if incoming_unit is None or exit_side is None:
        return target.position
    if target.mark_type == MarkType.LEEWARD:
        return ai_leeward_rounding_target(boat, target, incoming_unit, gate_unit, exit_side)

    return ai_standard_mark_rounding_target(boat, target, incoming_unit, gate_unit, exit_side)


def ai_standard_mark_rounding_target(
    boat: Boat,
    target: Mark,
    incoming_unit: Vector2,
    gate_unit: Vector2,
    exit_side: Vector2,
) -> Vector2:
    approach_side = port_rounding_boat_side(incoming_unit)
    target_to_boat = Vector2(boat.position.x - target.position.x, boat.position.y - target.position.y)
    if should_sail_to_mark_approach(target_to_boat, incoming_unit):
        return Vector2(
            target.position.x - incoming_unit.x * AI_MARK_APPROACH_DISTANCE + approach_side.x * AI_MARK_ROUNDING_OFFSET,
            target.position.y - incoming_unit.y * AI_MARK_APPROACH_DISTANCE + approach_side.y * AI_MARK_ROUNDING_OFFSET,
        )

    return Vector2(
        target.position.x + gate_unit.x * AI_MARK_EXIT_DISTANCE + exit_side.x * AI_MARK_ROUNDING_OFFSET,
        target.position.y + gate_unit.y * AI_MARK_EXIT_DISTANCE + exit_side.y * AI_MARK_ROUNDING_OFFSET,
    )


def ai_leeward_rounding_target(
    boat: Boat,
    target: Mark,
    incoming_unit: Vector2,
    gate_unit: Vector2,
    exit_side: Vector2,
) -> Vector2:
    approach_side = port_rounding_boat_side(incoming_unit)
    target_to_boat = Vector2(boat.position.x - target.position.x, boat.position.y - target.position.y)
    if should_sail_to_mark_approach(target_to_boat, incoming_unit):
        return Vector2(
            target.position.x - incoming_unit.x * AI_LEEWARD_ROUNDING_ADVANCE + approach_side.x * AI_LEEWARD_ROUNDING_OFFSET,
            target.position.y - incoming_unit.y * AI_LEEWARD_ROUNDING_ADVANCE + approach_side.y * AI_LEEWARD_ROUNDING_OFFSET,
        )

    return Vector2(
        target.position.x + gate_unit.x * AI_MARK_EXIT_DISTANCE + exit_side.x * AI_LEEWARD_ROUNDING_OFFSET,
        target.position.y + gate_unit.y * AI_MARK_EXIT_DISTANCE + exit_side.y * AI_LEEWARD_ROUNDING_OFFSET,
    )


def should_sail_to_mark_approach(
    target_to_boat: Vector2,
    incoming_unit: Vector2,
) -> bool:
    approach_progress = dot(target_to_boat, incoming_unit)
    return approach_progress < -AI_MARK_SWITCH_DISTANCE


def ai_finish_target_position(scenario: Scenario) -> Vector2:
    if scenario.course.race_format == RaceFormat.T3:
        return finish_position_for(scenario.course)
    return start_line_center(scenario)


def ai_finish_target_position_for_boat(boat: Boat, scenario: Scenario) -> Vector2:
    if scenario.course.race_format == RaceFormat.T3:
        return finish_position_for(scenario.course)

    start = scenario.course.start_line
    dx = start.committee_boat.x - start.pin.x
    dy = start.committee_boat.y - start.pin.y
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return start_line_center(scenario)

    center = start_line_center(scenario)
    side = boat.ai_board or 1
    offset = min(95.0, length * 0.48)
    return Vector2(center.x + (dx / length) * offset * side, center.y + (dy / length) * offset * side)


def best_vmg_heading(boat: Boat, scenario: Scenario, target_position: Vector2) -> float:
    from sailing_simulator.domain.wind import wind_at

    wind_direction, wind_speed = wind_at(scenario, boat.position)
    target_bearing = bearing_to(boat.position, target_position)
    best_heading = boat.heading_degrees
    best_score = -float("inf")

    for heading in range(0, 360, 5):
        twa = true_wind_angle(float(heading), wind_direction)
        speed = target_boat_speed(scenario.polar, wind_speed, twa)
        alignment = math.cos(math.radians(signed_angle(float(heading), target_bearing)))
        score = speed * alignment
        if score > best_score:
            best_score = score
            best_heading = float(heading)

    return best_heading


def reset_ai_board_if_needed(
    boat: Boat,
    scenario: Scenario,
    target_position: Vector2,
    leg_mode: str,
    wind_direction: float,
    wind_speed: float,
) -> None:
    if boat.ai_board is not None and boat.ai_board_target_leg_index == boat.target_leg_index:
        return

    boat.ai_board = best_ai_board(boat, scenario, target_position, leg_mode, wind_direction, wind_speed)
    boat.ai_board_target_leg_index = boat.target_leg_index
    boat.ai_last_maneuver_seconds = scenario.race_state.elapsed_seconds


def should_change_ai_board(
    boat: Boat,
    scenario: Scenario,
    target_position: Vector2,
    leg_mode: str,
    wind_direction: float,
    wind_speed: float,
) -> bool:
    if boat.ai_board is None:
        return True
    if distance(boat.position, target_position) <= AI_CLOSE_TARGET_RADIUS:
        return False
    if scenario.race_state.elapsed_seconds - boat.ai_last_maneuver_seconds < AI_MIN_MANEUVER_INTERVAL_SECONDS:
        return False
    if ai_board_near_boundary(boat, scenario, wind_direction, leg_mode):
        return True

    current_score = ai_board_vmg_score(boat, scenario, target_position, leg_mode, wind_direction, wind_speed, boat.ai_board)
    opposite_score = ai_board_vmg_score(boat, scenario, target_position, leg_mode, wind_direction, wind_speed, -boat.ai_board)
    return opposite_score > max(0.1, current_score * 1.35)


def ai_leg_mode(wind_direction: float, target_bearing: float) -> str:
    relative_to_wind = abs(signed_angle(wind_direction, target_bearing))
    return "downwind" if relative_to_wind > 100.0 else "upwind"


def best_ai_board(
    boat: Boat,
    scenario: Scenario,
    target_position: Vector2,
    leg_mode: str,
    wind_direction: float,
    wind_speed: float,
) -> int:
    first_score = ai_board_vmg_score(boat, scenario, target_position, leg_mode, wind_direction, wind_speed, 1)
    second_score = ai_board_vmg_score(boat, scenario, target_position, leg_mode, wind_direction, wind_speed, -1)
    return 1 if first_score >= second_score else -1


def ai_board_vmg_score(
    boat: Boat,
    scenario: Scenario,
    target_position: Vector2,
    leg_mode: str,
    wind_direction: float,
    wind_speed: float,
    board: int,
) -> float:
    heading = ai_board_heading(wind_direction, leg_mode, board)
    twa = true_wind_angle(heading, wind_direction)
    speed = target_boat_speed(scenario.polar, wind_speed, twa)
    alignment = math.cos(math.radians(signed_angle(heading, bearing_to(boat.position, target_position))))
    return speed * alignment - ai_mark_obstacle_penalty(boat, scenario, target_position, heading)


def ai_mark_obstacle_penalty(boat: Boat, scenario: Scenario, target_position: Vector2, heading: float) -> float:
    radians = math.radians(heading)
    projected = Vector2(
        boat.position.x + math.sin(radians) * AI_MARK_AVOIDANCE_LOOKAHEAD,
        boat.position.y - math.cos(radians) * AI_MARK_AVOIDANCE_LOOKAHEAD,
    )
    penalty = 0.0
    for mark in scenario.course.marks:
        if distance(mark.position, target_position) <= 1e-6:
            continue
        if distance_from_segment(mark.position, boat.position, projected) <= AI_MARK_AVOIDANCE_RADIUS:
            penalty += 100.0
    return penalty


def ai_board_heading(wind_direction: float, leg_mode: str, board: int) -> float:
    if leg_mode == "downwind":
        return normalize_degrees(wind_direction + 180.0 + board * AI_DOWNWIND_ANGLE)
    return normalize_degrees(wind_direction + board * AI_UPWIND_ANGLE)


def ai_board_near_boundary(boat: Boat, scenario: Scenario, wind_direction: float, leg_mode: str) -> bool:
    heading = ai_board_heading(wind_direction, leg_mode, boat.ai_board or 1)
    radians = math.radians(heading)
    projected = Vector2(
        boat.position.x + math.sin(radians) * AI_BOUNDARY_MARGIN,
        boat.position.y - math.cos(radians) * AI_BOUNDARY_MARGIN,
    )
    return (
        projected.x <= 0.0
        or projected.x >= scenario.course.boundary_width
        or projected.y <= 0.0
        or projected.y >= scenario.course.boundary_height
    )


def step_boat(boat: Boat, scenario: Scenario, elapsed_seconds: float) -> None:
    from sailing_simulator.domain.wind import wind_at

    if boat.is_finished:
        boat.speed_knots = 0.0
        append_track_point(boat)
        return

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


def bearing_to(origin: Vector2, target: Vector2) -> float:
    dx = target.x - origin.x
    dy = origin.y - target.y
    return normalize_degrees(math.degrees(math.atan2(dx, dy)))


def turn_toward_heading(current_heading: float, target_heading: float, max_degrees: float) -> float:
    delta = signed_angle(target_heading, current_heading)
    turn = max(-max_degrees, min(max_degrees, delta))
    return normalize_degrees(current_heading + turn)


def reset_boats_to_start(scenario: Scenario) -> None:
    base_x = min(scenario.course.start_line.pin.x, scenario.course.start_line.committee_boat.x) + 60.0
    base_y = max(scenario.course.start_line.pin.y, scenario.course.start_line.committee_boat.y) + 90.0
    for index, boat in enumerate(scenario.boats):
        boat.position = Vector2(base_x + index * 70.0, base_y + (index % 2) * 16.0)
        boat.heading_degrees = 315.0
        boat.speed_knots = 0.0
        boat.track = []
        boat.target_leg_index = 0
        boat.has_started = False
        boat.is_finished = False
        boat.finish_time_seconds = None
        boat.collision_stop_heading = None
        boat.collision_released_heading = None
        boat.ai_board = None
        boat.ai_board_target_leg_index = -1
        boat.ai_last_maneuver_seconds = -9999.0
        boat.ai_collision_escape_until_seconds = 0.0
        boat.ai_collision_escape_heading = None
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
                crossing = start_finish_line_crossing_parameter(scenario, previous, boat.position)
                if crossing is None or crossing + 1e-9 < segment_position:
                    break

                boat.has_started = True
                segment_position = crossing
                add_event(scenario, RaceEventType.START_CROSSED, f"{boat.name} started.")
                continue

            target = target_mark_for(scenario.course, boat.target_leg_index)
            if target is not None:
                rounding = mark_rounding_parameter(scenario, boat.target_leg_index, previous, boat.position)
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

            crossing = start_finish_line_crossing_parameter(scenario, previous, boat.position)
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
        if mark_rounding_parameter(scenario, boat.target_leg_index, previous, boat.position) is not None:
            boat.target_leg_index += 1
            add_event(
                scenario,
                RaceEventType.MARK_ROUNDED,
                f"{boat.name} rounded {target.label}.",
            )


def detect_boat_collisions(scenario: Scenario) -> None:
    colliding_boats: set[str] = set()
    for first, second in itertools.combinations(scenario.boats, 2):
        if first.is_finished or second.is_finished:
            continue
        if distance(first.position, second.position) <= BOAT_COLLISION_RADIUS:
            if boats_are_actively_escaping(first, second, scenario):
                continue
            colliding_boats.add(first.name)
            colliding_boats.add(second.name)
            set_collision_escape(first, second, scenario)
            set_collision_escape(second, first, scenario)
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


def boats_are_actively_escaping(first: Boat, second: Boat, scenario: Scenario) -> bool:
    return (
        first.control_mode == BoatControlMode.AI
        and second.control_mode == BoatControlMode.AI
        and first.ai_collision_escape_heading is not None
        and second.ai_collision_escape_heading is not None
        and scenario.race_state.elapsed_seconds < first.ai_collision_escape_until_seconds
        and scenario.race_state.elapsed_seconds < second.ai_collision_escape_until_seconds
    )


def detect_mark_collisions(scenario: Scenario) -> None:
    for boat in scenario.boats:
        target = target_mark_for(scenario.course, boat.target_leg_index)
        if target is None:
            continue
        if distance(boat.position, target.position) <= MARK_COLLISION_RADIUS:
            add_event(
                scenario,
                RaceEventType.MARK_COLLISION,
                f"{boat.name} hit mark {target.label}.",
            )


def add_event(scenario: Scenario, event_type: RaceEventType, message: str) -> None:
    scenario.race_state.events.append(
        RaceEvent(
            event_type=event_type,
            message=message,
            elapsed_seconds=scenario.race_state.elapsed_seconds,
        )
    )


def set_collision_escape(boat: Boat, other: Boat, scenario: Scenario) -> None:
    from sailing_simulator.domain.wind import wind_at

    if boat.control_mode != BoatControlMode.AI:
        return
    if scenario.race_state.elapsed_seconds < boat.ai_collision_escape_until_seconds:
        return

    away_heading = bearing_to(other.position, boat.position)
    if distance(boat.position, other.position) < 1e-6:
        away_heading = normalize_degrees(boat.heading_degrees + 90.0)
    target_position = ai_target_position(boat, scenario)
    wind_direction, _ = wind_at(scenario, boat.position)
    leg_mode = ai_leg_mode(wind_direction, bearing_to(boat.position, target_position))
    first_heading = ai_board_heading(wind_direction, leg_mode, 1)
    second_heading = ai_board_heading(wind_direction, leg_mode, -1)
    first_alignment = math.cos(math.radians(signed_angle(first_heading, away_heading)))
    second_alignment = math.cos(math.radians(signed_angle(second_heading, away_heading)))
    boat.ai_board = 1 if first_alignment >= second_alignment else -1
    boat.ai_board_target_leg_index = boat.target_leg_index
    boat.ai_collision_escape_heading = ai_board_heading(wind_direction, leg_mode, boat.ai_board)
    boat.ai_collision_escape_until_seconds = scenario.race_state.elapsed_seconds + collision_escape_duration(boat, other, scenario)
    boat.ai_last_maneuver_seconds = boat.ai_collision_escape_until_seconds


def clamp_boats_to_course(scenario: Scenario) -> None:
    for boat in scenario.boats:
        clamped_position = clamp_to_course(boat.position, scenario.course.boundary_width, scenario.course.boundary_height)
        if clamped_position != boat.position:
            boat.position = clamped_position
            boat.speed_knots = 0.0


def stop_for_collision(boat: Boat) -> None:
    if boat.collision_released_heading is not None:
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


def mark_rounding_parameter(
    scenario: Scenario,
    target_leg_index: int,
    segment_start: Vector2,
    segment_end: Vector2,
) -> float | None:
    target = target_mark_for(scenario.course, target_leg_index)
    if target is None:
        return None

    side_unit = rounding_boat_side_unit(scenario, target_leg_index)
    gate_unit = mark_rounding_gate_unit_for(scenario, target_leg_index)
    if side_unit is None or gate_unit is None:
        return mark_crossing_parameter(target.position, segment_start, segment_end, MARK_COLLISION_RADIUS)

    start_advance = dot(Vector2(segment_start.x - target.position.x, segment_start.y - target.position.y), gate_unit)
    end_advance = dot(Vector2(segment_end.x - target.position.x, segment_end.y - target.position.y), gate_unit)
    end_offset = Vector2(segment_end.x - target.position.x, segment_end.y - target.position.y)
    if start_advance >= MARK_ROUNDING_ADVANCE_DISTANCE:
        return completed_mark_rounding_parameter(end_offset, side_unit, gate_unit)
    if end_advance < MARK_ROUNDING_ADVANCE_DISTANCE:
        return None

    advance_delta = end_advance - start_advance
    if abs(advance_delta) < 1e-9:
        return None

    parameter = (MARK_ROUNDING_ADVANCE_DISTANCE - start_advance) / advance_delta
    if not 0.0 <= parameter <= 1.0:
        return None

    crossing_point = point_at_parameter(segment_start, segment_end, parameter)
    target_to_crossing = Vector2(crossing_point.x - target.position.x, crossing_point.y - target.position.y)
    if dot(target_to_crossing, side_unit) < 0.0 or abs(cross(target_to_crossing, gate_unit)) > MARK_ROUNDING_GATE_HALF_WIDTH:
        return None
    return parameter


def completed_mark_rounding_parameter(target_to_boat: Vector2, side_unit: Vector2, gate_unit: Vector2) -> float | None:
    if (
        dot(target_to_boat, gate_unit) >= MARK_ROUNDING_ADVANCE_DISTANCE
        and dot(target_to_boat, gate_unit) <= MARK_ROUNDING_COMPLETION_MAX_ADVANCE
        and dot(target_to_boat, side_unit) >= 0.0
        and abs(cross(target_to_boat, gate_unit)) <= MARK_ROUNDING_GATE_HALF_WIDTH
    ):
        return 1.0
    return None


def incoming_leg_unit_for(scenario: Scenario, target_leg_index: int) -> Vector2 | None:
    target = target_mark_for(scenario.course, target_leg_index)
    if target is None:
        return None

    origin = leg_origin_for(scenario, target_leg_index)
    leg = Vector2(target.position.x - origin.x, target.position.y - origin.y)
    leg_length = math.hypot(leg.x, leg.y)
    if leg_length < 1e-9:
        return None
    return Vector2(leg.x / leg_length, leg.y / leg_length)


def outgoing_leg_unit_for(scenario: Scenario, target_leg_index: int) -> Vector2 | None:
    target = target_mark_for(scenario.course, target_leg_index)
    exit_target = rounding_exit_target_position(scenario, target_leg_index)
    if target is None or exit_target is None:
        return None

    leg = Vector2(exit_target.x - target.position.x, exit_target.y - target.position.y)
    leg_length = math.hypot(leg.x, leg.y)
    if leg_length < 1e-9:
        return None
    return Vector2(leg.x / leg_length, leg.y / leg_length)


def mark_rounding_gate_unit_for(scenario: Scenario, target_leg_index: int) -> Vector2 | None:
    target = target_mark_for(scenario.course, target_leg_index)
    if target is None:
        return None
    if target.mark_type in {MarkType.WINDWARD, MarkType.LEEWARD}:
        return Vector2(0.0, -1.0)
    return outgoing_leg_unit_for(scenario, target_leg_index)


def rounding_exit_target_position(scenario: Scenario, target_leg_index: int) -> Vector2 | None:
    next_target = target_mark_for(scenario.course, target_leg_index + 1)
    if next_target is not None:
        return next_target.position
    if scenario.course.race_format == RaceFormat.T3:
        return finish_position_for(scenario.course)
    return start_line_center(scenario)


def rounding_boat_side_unit(scenario: Scenario, target_leg_index: int) -> Vector2 | None:
    rounding_exit_unit = outgoing_leg_unit_for(scenario, target_leg_index)
    if rounding_exit_unit is not None:
        return port_rounding_boat_side(rounding_exit_unit)

    incoming_unit = incoming_leg_unit_for(scenario, target_leg_index)
    if incoming_unit is None:
        return None
    return port_rounding_boat_side(incoming_unit)


def port_rounding_boat_side(incoming_unit: Vector2) -> Vector2:
    return Vector2(-incoming_unit.y, incoming_unit.x)


def collision_escape_duration(boat: Boat, other: Boat, scenario: Scenario) -> float:
    seed = (
        int(scenario.race_state.elapsed_seconds * 1000.0)
        + int(boat.position.x * 11.0 + boat.position.y * 17.0)
        + int(other.position.x * 23.0 + other.position.y * 29.0)
        + sum(ord(character) for character in boat.name)
        + sum(ord(character) * 3 for character in other.name)
    )
    generator = random.Random(seed)
    return generator.uniform(AI_COLLISION_ESCAPE_MIN_SECONDS, AI_COLLISION_ESCAPE_MAX_SECONDS)


def leg_origin_for(scenario: Scenario, target_leg_index: int) -> Vector2:
    if target_leg_index <= 0:
        return start_line_center(scenario)

    previous_target = target_mark_for(scenario.course, target_leg_index - 1)
    if previous_target is not None:
        return previous_target.position
    return finish_position_for(scenario.course)


def start_line_center(scenario: Scenario) -> Vector2:
    start = scenario.course.start_line
    return Vector2(
        (start.pin.x + start.committee_boat.x) * 0.5,
        (start.pin.y + start.committee_boat.y) * 0.5,
    )


def start_finish_line_crossing_parameter(scenario: Scenario, segment_start: Vector2, segment_end: Vector2) -> float | None:
    line_start, line_end = extended_start_finish_line(scenario)
    crossing = segment_intersection_parameter(segment_start, segment_end, line_start, line_end)
    if crossing is not None:
        return crossing
    if distance_from_segment(segment_end, line_start, line_end) <= START_FINISH_LINE_TOUCH_RADIUS:
        return 1.0
    return None


def extended_start_finish_line(scenario: Scenario) -> tuple[Vector2, Vector2]:
    start = scenario.course.start_line
    dx = start.committee_boat.x - start.pin.x
    dy = start.committee_boat.y - start.pin.y
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return start.pin, start.committee_boat

    extension_x = dx / length * START_FINISH_LINE_EXTENSION
    extension_y = dy / length * START_FINISH_LINE_EXTENSION
    return (
        Vector2(start.pin.x - extension_x, start.pin.y - extension_y),
        Vector2(start.committee_boat.x + extension_x, start.committee_boat.y + extension_y),
    )


def finish_mark_crossing_parameter(scenario: Scenario, segment_start: Vector2, segment_end: Vector2) -> float | None:
    finish_mark = finish_mark_for(scenario)
    if finish_mark is None:
        return None
    return mark_crossing_parameter(finish_mark.position, segment_start, segment_end, MARK_COLLISION_RADIUS)


def finish_mark_for(scenario: Scenario) -> Mark | None:
    if scenario.course.race_format != RaceFormat.T3:
        return None

    explicit_finish = next((mark for mark in scenario.course.marks if mark.mark_type == MarkType.FINISH), None)
    if explicit_finish is not None:
        return explicit_finish
    return None


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
