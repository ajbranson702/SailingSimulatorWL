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
    Scenario,
    Vector2,
)
from sailing_simulator.domain.race_progress import finish_position_for, target_mark_for, total_targets_for

MIN_UPWIND_ANGLE_DEGREES = 45.0
COURSE_UNITS_PER_NAUTICAL_MILE = 1800.0
MAX_TRACK_POINTS = 300
BOAT_COLLISION_RADIUS = 28.0
BOAT_LENGTH_UNITS = 28.0
MARK_COLLISION_RADIUS = 22.0
START_FINISH_LINE_EXTENSION = 45.0
START_FINISH_LINE_TOUCH_RADIUS = 18.0
MARK_ROUNDING_GATE_HALF_WIDTH = 140.0
MARK_ROUNDING_ADVANCE_DISTANCE = 4.0
MARK_ROUNDING_COMPLETION_MAX_ADVANCE = 260.0
MARK_APPROACH_CONFIRM_DISTANCE = 4.0
MARK_ROOM_ZONE_RADIUS = BOAT_LENGTH_UNITS * 3.0
MARK_ROOM_OVERLAP_DISTANCE = BOAT_LENGTH_UNITS * 1.25
AI_MARK_ROUNDING_OFFSET = 112.0
AI_MARK_APPROACH_DISTANCE = 95.0
AI_MARK_EXIT_DISTANCE = 65.0
AI_LEEWARD_ROUNDING_OFFSET = 80.0
AI_LEEWARD_ROUNDING_ADVANCE = 92.0
AI_CLOSE_TARGET_RADIUS = 85.0
AI_FINISH_APPROACH_RADIUS = 260.0
AI_FINISH_FETCH_DISTANCE = 420.0
AI_FINISH_RECONSIDER_SECONDS = 26.0
AI_ROUNDING_WAYPOINT_RADIUS = 70.0
AI_MARK_TRAFFIC_ZONE_RADIUS = AI_MARK_APPROACH_DISTANCE + AI_MARK_ROUNDING_OFFSET + BOAT_LENGTH_UNITS
AI_BOUNDARY_MARGIN = 75.0
AI_MARK_AVOIDANCE_LOOKAHEAD = 140.0
AI_MARK_AVOIDANCE_RADIUS = 42.0
AI_MIN_MANEUVER_INTERVAL_SECONDS = 18.0
AI_COLLISION_ESCAPE_MIN_SECONDS = 10.0
AI_COLLISION_ESCAPE_MAX_SECONDS = 28.0
AI_UPWIND_ANGLE = 45.0
AI_DOWNWIND_ANGLE = 35.0
AI_START_STRATEGIES = ("middle", "committee", "pin", "port")
AI_COLLISION_AVOIDANCE_LOOKAHEAD_SECONDS = 4.0
AI_COLLISION_AVOIDANCE_TRIGGER_DISTANCE = BOAT_COLLISION_RADIUS + BOAT_LENGTH_UNITS * 0.75
AI_TACTICAL_WAYPOINT_VARIATION = 34.0
AI_TACTICAL_SCORE_BIAS = 0.32
AI_BOARD_CHANGE_RATIO = 1.35
AI_BOARD_CHANGE_RATIO_VARIATION = 0.22
PENALTY_TURN_DEGREES_PER_TURN = 360.0
PENALTY_TURN_RATE_DEGREES_PER_SECOND = 45.0
AI_PENALTY_CLEAR_DISTANCE = BOAT_LENGTH_UNITS * 3.0
USER_TACK_TURN_RATE_DEGREES_PER_SECOND = 38.0
USER_GYBE_TURN_RATE_DEGREES_PER_SECOND = 58.0
USER_TACK_INITIAL_SPEED_FACTOR = 0.55
USER_GYBE_INITIAL_SPEED_FACTOR = 0.72
USER_TACK_TARGET_SPEED_FACTOR = 0.62
USER_GYBE_TARGET_SPEED_FACTOR = 0.78


def step_scenario(scenario: Scenario, elapsed_seconds: float) -> None:
    from sailing_simulator.domain.wind import update_wind_field

    clamp_boats_to_course(scenario)
    previous_positions = {boat.name: boat.position for boat in scenario.boats}
    scenario.race_state.events = []
    scenario.race_state.elapsed_seconds += elapsed_seconds
    if abs(scenario.race_state.elapsed_seconds) < 1e-9:
        scenario.race_state.elapsed_seconds = 0.0
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

    if boat.penalty_turn_remaining_degrees > 0.0:
        return

    if boat.penalty_turns_owed > 0 and ai_boat_is_clear_for_penalty(boat):
        start_penalty_turn_if_owed(boat)
        return

    if not boat.has_started and scenario.race_state.elapsed_seconds < 0.0:
        target_position = ai_prestart_target_position_for_boat(boat, scenario)
        desired_heading = best_vmg_heading(boat, scenario, target_position)
        boat.heading_degrees = turn_toward_heading(boat.heading_degrees, desired_heading, 18.0)
        release_collision_stop_if_heading_changed(boat)
        return

    if boat.ai_collision_escape_heading is not None:
        if scenario.race_state.elapsed_seconds < boat.ai_collision_escape_until_seconds:
            boat.heading_degrees = turn_toward_heading(boat.heading_degrees, boat.ai_collision_escape_heading, 30.0)
            release_collision_stop_if_heading_changed(boat)
            return
        boat.ai_collision_escape_heading = None

    if boat_is_on_finish_approach(boat, scenario):
        desired_heading = ai_finish_approach_heading(boat, scenario)
        boat.heading_degrees = turn_toward_heading(boat.heading_degrees, desired_heading, 18.0)
        release_collision_stop_if_heading_changed(boat)
        return

    avoidance_maneuver = collision_avoidance_maneuver(boat, scenario)
    if avoidance_maneuver == "tack":
        tack(boat, wind_at(scenario, boat.position)[0])
        boat.ai_board = -boat.ai_board if boat.ai_board is not None else None
        boat.ai_last_maneuver_seconds = scenario.race_state.elapsed_seconds
        return
    if avoidance_maneuver == "gybe":
        gybe(boat, wind_at(scenario, boat.position)[0])
        boat.ai_board = -boat.ai_board if boat.ai_board is not None else None
        boat.ai_last_maneuver_seconds = scenario.race_state.elapsed_seconds
        return

    target_position = ai_target_position(boat, scenario)
    wind_direction, wind_speed = wind_at(scenario, boat.position)
    leg_mode = ai_leg_mode(wind_direction, bearing_to(boat.position, target_position))
    steering_target = ai_steering_target_position(boat, scenario)
    if leg_mode == "reach" and boat.collision_stop_heading is None:
        if (
            boat.ai_board is not None
            and scenario.race_state.elapsed_seconds - boat.ai_last_maneuver_seconds >= AI_MIN_MANEUVER_INTERVAL_SECONDS
            and ai_board_near_boundary(boat, scenario, wind_direction, leg_mode)
        ):
            boat.ai_board = -boat.ai_board
            boat.ai_last_maneuver_seconds = scenario.race_state.elapsed_seconds
            desired_heading = ai_board_heading(wind_direction, leg_mode, boat.ai_board)
        else:
            desired_heading = best_vmg_heading(boat, scenario, steering_target)
        boat.heading_degrees = turn_toward_heading(boat.heading_degrees, desired_heading, 18.0)
        release_collision_stop_if_heading_changed(boat)
        return

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

    if boat.collision_stop_heading is None and (
        distance(boat.position, target_position) <= AI_CLOSE_TARGET_RADIUS
        or boat.mark_approach_target_leg_index == boat.target_leg_index
    ):
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
        if scenario.race_state.elapsed_seconds < 0.0:
            return ai_prestart_target_position_for_boat(boat, scenario)
        return first_ai_target_position(scenario)

    target = target_mark_for(scenario.course, boat.target_leg_index)
    if target is not None:
        return target.position
    return ai_finish_target_position_for_boat(boat, scenario)


def ai_steering_target_position(boat: Boat, scenario: Scenario) -> Vector2:
    if not boat.has_started and scenario.race_state.elapsed_seconds < 0.0:
        return ai_prestart_target_position_for_boat(boat, scenario)

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
    outgoing_unit = outgoing_leg_unit_for(scenario, target_index)
    if incoming_unit is None or gate_unit is None or outgoing_unit is None:
        return target.position

    exit_side = rounding_boat_side_unit(scenario, target_index)
    if exit_side is None:
        return target.position
    approach_confirmed = boat.mark_approach_target_leg_index == target_index
    if target.mark_type == MarkType.LEEWARD:
        return ai_leeward_rounding_target(boat, target, incoming_unit, outgoing_unit, exit_side, approach_confirmed)

    return ai_standard_mark_rounding_target(boat, target, incoming_unit, outgoing_unit, exit_side, approach_confirmed)


def ai_standard_mark_rounding_target(
    boat: Boat,
    target: Mark,
    incoming_unit: Vector2,
    outgoing_unit: Vector2,
    exit_side: Vector2,
    approach_confirmed: bool,
) -> Vector2:
    approach_distance = approach_distance_for_boat(boat, AI_MARK_APPROACH_DISTANCE)
    rounding_offset = rounding_offset_for_boat(boat, AI_MARK_ROUNDING_OFFSET)
    return ai_staged_mark_rounding_target(
        boat,
        target,
        incoming_unit,
        outgoing_unit,
        exit_side,
        approach_confirmed,
        approach_distance,
        rounding_offset,
    )


def ai_leeward_rounding_target(
    boat: Boat,
    target: Mark,
    incoming_unit: Vector2,
    outgoing_unit: Vector2,
    exit_side: Vector2,
    approach_confirmed: bool,
) -> Vector2:
    approach_distance = approach_distance_for_boat(boat, AI_LEEWARD_ROUNDING_ADVANCE)
    rounding_offset = rounding_offset_for_boat(boat, AI_LEEWARD_ROUNDING_OFFSET)
    return ai_staged_mark_rounding_target(
        boat,
        target,
        incoming_unit,
        outgoing_unit,
        exit_side,
        approach_confirmed,
        approach_distance,
        rounding_offset,
    )


def ai_staged_mark_rounding_target(
    boat: Boat,
    target: Mark,
    incoming_unit: Vector2,
    outgoing_unit: Vector2,
    exit_side: Vector2,
    approach_confirmed: bool,
    approach_distance: float,
    rounding_offset: float,
) -> Vector2:
    approach_side = port_rounding_boat_side(incoming_unit)
    approach_target = Vector2(
        target.position.x + incoming_unit.x * approach_distance + approach_side.x * rounding_offset,
        target.position.y + incoming_unit.y * approach_distance + approach_side.y * rounding_offset,
    )
    wrap_target = Vector2(
        target.position.x + incoming_unit.x * approach_distance + exit_side.x * rounding_offset,
        target.position.y + incoming_unit.y * approach_distance + exit_side.y * rounding_offset,
    )
    exit_target = Vector2(
        target.position.x + outgoing_unit.x * AI_MARK_EXIT_DISTANCE + exit_side.x * rounding_offset,
        target.position.y + outgoing_unit.y * AI_MARK_EXIT_DISTANCE + exit_side.y * rounding_offset,
    )

    reset_ai_rounding_stage_if_needed(boat)
    if approach_confirmed or distance(boat.position, approach_target) <= AI_ROUNDING_WAYPOINT_RADIUS:
        boat.ai_rounding_stage = max(boat.ai_rounding_stage, 1)
    if boat.ai_rounding_stage >= 1 and distance(boat.position, wrap_target) <= AI_ROUNDING_WAYPOINT_RADIUS:
        boat.ai_rounding_stage = 2

    if boat.ai_rounding_stage <= 0:
        return approach_target
    if boat.ai_rounding_stage == 1:
        return wrap_target
    return exit_target


def reset_ai_rounding_stage_if_needed(boat: Boat) -> None:
    if boat.ai_rounding_target_leg_index == boat.target_leg_index:
        return
    boat.ai_rounding_target_leg_index = boat.target_leg_index
    boat.ai_rounding_stage = 0


def approach_distance_for_boat(boat: Boat, base_distance: float) -> float:
    variation = ai_tactical_value(boat, "approach") * AI_TACTICAL_WAYPOINT_VARIATION
    return max(base_distance * 0.65, base_distance + variation)


def rounding_offset_for_boat(boat: Boat, base_offset: float) -> float:
    variation = ai_tactical_value(boat, "rounding") * AI_TACTICAL_WAYPOINT_VARIATION
    return max(base_offset * 0.65, base_offset + variation)


def ai_finish_target_position(scenario: Scenario) -> Vector2:
    return start_line_center(scenario)


def ai_finish_target_position_for_boat(boat: Boat, scenario: Scenario) -> Vector2:
    start = scenario.course.start_line
    dx = start.committee_boat.x - start.pin.x
    dy = start.committee_boat.y - start.pin.y
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return start_line_center(scenario)

    center = start_line_center(scenario)
    side = 1 if ai_tactical_value(boat, "finish-side") >= 0.0 else -1
    lane_variation = ai_tactical_value(boat, "finish-lane") * 0.08
    offset = length * max(0.18, min(0.34, 0.26 + lane_variation)) * side
    return Vector2(center.x + (dx / length) * offset, center.y + (dy / length) * offset)


def ai_finish_approach_heading(boat: Boat, scenario: Scenario) -> float:
    from sailing_simulator.domain.wind import wind_at

    target_position = ai_finish_target_position_for_boat(boat, scenario)
    wind_direction, wind_speed = wind_at(scenario, boat.position)
    leg_mode = ai_leg_mode(wind_direction, bearing_to(boat.position, target_position))
    if leg_mode == "reach":
        return best_vmg_heading(boat, scenario, target_position)

    if (
        boat.ai_board is None
        or boat.ai_board_target_leg_index != boat.target_leg_index
        or should_reconsider_finish_board(boat, scenario, leg_mode, wind_direction)
    ):
        boat.ai_board = best_finish_board(boat, scenario, leg_mode, wind_direction, wind_speed)
        boat.ai_board_target_leg_index = boat.target_leg_index
        boat.ai_last_maneuver_seconds = scenario.race_state.elapsed_seconds

    return ai_board_heading(wind_direction, leg_mode, boat.ai_board or 1)


def should_reconsider_finish_board(boat: Boat, scenario: Scenario, leg_mode: str, wind_direction: float) -> bool:
    if boat.ai_board is None:
        return True
    if finish_board_fetches_line(boat, scenario, leg_mode, wind_direction, boat.ai_board):
        return False
    if scenario.race_state.elapsed_seconds - boat.ai_last_maneuver_seconds < AI_FINISH_RECONSIDER_SECONDS:
        return False
    return ai_board_near_boundary(boat, scenario, wind_direction, leg_mode)


def best_finish_board(
    boat: Boat,
    scenario: Scenario,
    leg_mode: str,
    wind_direction: float,
    wind_speed: float,
) -> int:
    first_score = finish_board_score(boat, scenario, leg_mode, wind_direction, wind_speed, 1)
    second_score = finish_board_score(boat, scenario, leg_mode, wind_direction, wind_speed, -1)
    return 1 if first_score >= second_score else -1


def finish_board_score(
    boat: Boat,
    scenario: Scenario,
    leg_mode: str,
    wind_direction: float,
    wind_speed: float,
    board: int,
) -> float:
    heading = ai_board_heading(wind_direction, leg_mode, board)
    target_position = ai_finish_target_position_for_boat(boat, scenario)
    target_bearing = bearing_to(boat.position, target_position)
    twa = true_wind_angle(heading, wind_direction)
    speed = target_boat_speed(scenario.polar, wind_speed, twa)
    alignment = math.cos(math.radians(signed_angle(heading, target_bearing)))
    crossing_point = finish_crossing_point_for_heading(boat.position, heading, scenario)
    if crossing_point is None:
        return speed * alignment

    lane_error = distance(crossing_point, target_position)
    return 100.0 + speed * alignment - lane_error * 0.04


def finish_board_fetches_line(
    boat: Boat,
    scenario: Scenario,
    leg_mode: str,
    wind_direction: float,
    board: int,
) -> bool:
    heading = ai_board_heading(wind_direction, leg_mode, board)
    return finish_crossing_point_for_heading(boat.position, heading, scenario) is not None


def finish_crossing_point_for_heading(position: Vector2, heading: float, scenario: Scenario) -> Vector2 | None:
    radians = math.radians(heading)
    projected = Vector2(
        position.x + math.sin(radians) * AI_FINISH_FETCH_DISTANCE,
        position.y - math.cos(radians) * AI_FINISH_FETCH_DISTANCE,
    )
    crossing = finish_line_crossing_parameter(scenario, position, projected)
    if crossing is None:
        return None
    return point_at_parameter(position, projected, crossing)


def ai_prestart_target_position_for_boat(boat: Boat, scenario: Scenario) -> Vector2:
    start = scenario.course.start_line
    dx = start.committee_boat.x - start.pin.x
    dy = start.committee_boat.y - start.pin.y
    line_length = math.hypot(dx, dy)
    if line_length < 1e-9:
        return boat.position

    line_unit = Vector2(dx / line_length, dy / line_length)
    center = start_line_center(scenario)
    prestart_side = prestart_side_unit(scenario)
    strategy = ai_start_strategy_for_boat(boat, scenario)
    sequence_remaining = max(0.0, -scenario.race_state.elapsed_seconds)

    lane_fraction = ai_start_lane_fraction(strategy)
    patrol_width = ai_start_patrol_width(strategy)
    if sequence_remaining > 18.0:
        lane_fraction += math.sin(ai_start_patrol_phase(boat, scenario)) * patrol_width
    elif strategy == "port":
        lane_fraction = -0.22

    depth = ai_start_depth(strategy, sequence_remaining)
    if boat.is_early_start:
        depth = 150.0

    lane_fraction = max(-0.48, min(0.48, lane_fraction))
    along_offset = lane_fraction * line_length

    return Vector2(
        center.x + line_unit.x * along_offset + prestart_side.x * depth,
        center.y + line_unit.y * along_offset + prestart_side.y * depth,
    )


def ai_start_strategy_for_boat(boat: Boat, scenario: Scenario) -> str:
    if boat.ai_start_strategy in AI_START_STRATEGIES:
        return boat.ai_start_strategy

    ai_boats = [candidate for candidate in scenario.boats if candidate.control_mode == BoatControlMode.AI]
    index = ai_boats.index(boat) if boat in ai_boats else 0
    boat.ai_start_strategy = AI_START_STRATEGIES[index % len(AI_START_STRATEGIES)]
    return boat.ai_start_strategy


def ai_start_lane_fraction(strategy: str) -> float:
    lanes = {
        "pin": -0.38,
        "port": -0.44,
        "middle": 0.0,
        "committee": 0.36,
    }
    return lanes.get(strategy, 0.0)


def ai_start_patrol_width(strategy: str) -> float:
    widths = {
        "pin": 0.16,
        "port": 0.12,
        "middle": 0.26,
        "committee": 0.14,
    }
    return widths.get(strategy, 0.18)


def ai_start_patrol_phase(boat: Boat, scenario: Scenario) -> float:
    index = scenario.boats.index(boat) if boat in scenario.boats else 0
    return scenario.race_state.elapsed_seconds / 8.0 + index * 1.7


def ai_start_depth(strategy: str, sequence_remaining: float) -> float:
    if strategy == "port":
        if sequence_remaining > 35.0:
            return 140.0
        if sequence_remaining > 12.0:
            return 86.0
        return 34.0
    if strategy == "committee":
        if sequence_remaining > 35.0:
            return 120.0
        if sequence_remaining > 12.0:
            return 76.0
        return 30.0
    if sequence_remaining > 35.0:
        return 115.0
    if sequence_remaining > 12.0:
        return 70.0
    return 32.0


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
    change_ratio = AI_BOARD_CHANGE_RATIO + ai_tactical_value(boat, "maneuver-threshold") * AI_BOARD_CHANGE_RATIO_VARIATION
    return opposite_score > max(0.1, current_score * change_ratio)


def boat_is_on_finish_approach(boat: Boat, scenario: Scenario) -> bool:
    if not boat.has_started or boat.is_finished:
        return False
    if target_mark_for(scenario.course, boat.target_leg_index) is not None:
        return False

    line_start, line_end = extended_start_finish_line(scenario)
    return distance_from_segment(boat.position, line_start, line_end) <= AI_FINISH_APPROACH_RADIUS


def should_tack_to_avoid_collision(boat: Boat, scenario: Scenario) -> bool:
    return collision_avoidance_maneuver(boat, scenario) == "tack"


def collision_avoidance_maneuver(boat: Boat, scenario: Scenario) -> str | None:
    for other in scenario.boats:
        if other is boat or other.is_finished or other.penalty_turn_remaining_degrees > 0.0:
            continue
        if distance(boat.position, other.position) > AI_COLLISION_AVOIDANCE_TRIGGER_DISTANCE:
            continue
        if not boats_have_projected_collision(boat, other, AI_COLLISION_AVOIDANCE_LOOKAHEAD_SECONDS):
            continue
        mark_room_keep_clear = mark_room_keep_clear_boat(boat, other, scenario)
        if mark_room_keep_clear is boat:
            return avoidance_maneuver_for_leg(boat, scenario)
        if mark_room_keep_clear is other:
            continue
        if boats_are_in_same_mark_traffic_zone(boat, other, scenario):
            continue
        if boat_should_keep_clear(boat, other, scenario):
            return avoidance_maneuver_for_leg(boat, scenario)
    return None


def boat_should_keep_clear(boat: Boat, other: Boat, scenario: Scenario) -> bool:
    boat_tack = tack_side(boat, scenario)
    other_tack = tack_side(other, scenario)
    if boat_tack != other_tack:
        return (
            boat_is_on_upwind_leg(boat, scenario)
            and boat_is_on_upwind_leg(other, scenario)
            and boat_tack == "port"
            and other_tack == "starboard"
        )

    return windward_boat(boat, other, scenario) is boat


def mark_room_keep_clear_boat(first: Boat, second: Boat, scenario: Scenario) -> Boat | None:
    target = common_mark_room_target(first, second, scenario)
    if target is None:
        return None
    if mark_room_excluded_by_opposite_tacks(first, second, scenario, target):
        return None
    if not boats_are_in_mark_room_zone(first, second, target):
        return None

    if boats_are_overlapped_at_mark(first, second, scenario):
        inside = inside_boat_at_mark(first, second, scenario, target)
        return second if inside is first else first

    first_distance = distance(first.position, target.position)
    second_distance = distance(second.position, target.position)
    if abs(first_distance - second_distance) <= 1e-9:
        return None
    return second if first_distance < second_distance else first


def common_mark_room_target(first: Boat, second: Boat, scenario: Scenario) -> Mark | None:
    if not first.has_started or not second.has_started:
        return None
    if first.target_leg_index != second.target_leg_index:
        return None

    target = target_mark_for(scenario.course, first.target_leg_index)
    if target is None:
        return None

    first_side = rounding_boat_side_unit(scenario, first.target_leg_index)
    second_side = rounding_boat_side_unit(scenario, second.target_leg_index)
    if first_side is None or second_side is None:
        return None
    if dot(first_side, second_side) < 0.99:
        return None
    return target


def mark_room_excluded_by_opposite_tacks(first: Boat, second: Boat, scenario: Scenario, target: Mark) -> bool:
    if target.mark_type != MarkType.WINDWARD:
        return False
    return tack_side(first, scenario) != tack_side(second, scenario) and boats_are_on_upwind_leg(first, second, scenario)


def boats_are_in_mark_room_zone(first: Boat, second: Boat, target: Mark) -> bool:
    return distance(first.position, target.position) <= MARK_ROOM_ZONE_RADIUS or distance(second.position, target.position) <= MARK_ROOM_ZONE_RADIUS


def boats_are_overlapped_at_mark(first: Boat, second: Boat, scenario: Scenario) -> bool:
    axis = incoming_leg_unit_for(scenario, first.target_leg_index)
    if axis is None:
        axis = heading_unit(midpoint_heading(first.heading_degrees, second.heading_degrees))

    separation = Vector2(second.position.x - first.position.x, second.position.y - first.position.y)
    return abs(dot(separation, axis)) <= MARK_ROOM_OVERLAP_DISTANCE


def inside_boat_at_mark(first: Boat, second: Boat, scenario: Scenario, target: Mark) -> Boat:
    first_distance = distance(first.position, target.position)
    second_distance = distance(second.position, target.position)
    if abs(first_distance - second_distance) > 1e-9:
        return first if first_distance < second_distance else second

    side_unit = rounding_boat_side_unit(scenario, first.target_leg_index)
    if side_unit is None:
        return first
    first_side = dot(Vector2(first.position.x - target.position.x, first.position.y - target.position.y), side_unit)
    second_side = dot(Vector2(second.position.x - target.position.x, second.position.y - target.position.y), side_unit)
    return first if first_side >= second_side else second


def avoidance_maneuver_for_leg(boat: Boat, scenario: Scenario) -> str:
    return "tack" if boat_is_on_upwind_leg(boat, scenario) else "gybe"


def boats_are_in_same_mark_traffic_zone(first: Boat, second: Boat, scenario: Scenario) -> bool:
    if first.target_leg_index != second.target_leg_index:
        return False

    target = target_mark_for(scenario.course, first.target_leg_index)
    if target is None:
        return False

    return (
        distance(first.position, target.position) <= AI_MARK_TRAFFIC_ZONE_RADIUS
        and distance(second.position, target.position) <= AI_MARK_TRAFFIC_ZONE_RADIUS
    )


def boats_have_projected_collision(first: Boat, second: Boat, lookahead_seconds: float) -> bool:
    first_velocity = velocity_units_per_second(first)
    second_velocity = velocity_units_per_second(second)
    relative_position = Vector2(second.position.x - first.position.x, second.position.y - first.position.y)
    relative_velocity = Vector2(second_velocity.x - first_velocity.x, second_velocity.y - first_velocity.y)
    relative_speed_squared = dot(relative_velocity, relative_velocity)
    if relative_speed_squared < 1e-9:
        return False

    closing_rate = dot(relative_position, relative_velocity)
    if closing_rate >= 0.0:
        return False

    closest_time = max(0.0, min(lookahead_seconds, -closing_rate / relative_speed_squared))
    closest_position = Vector2(
        relative_position.x + relative_velocity.x * closest_time,
        relative_position.y + relative_velocity.y * closest_time,
    )
    return math.hypot(closest_position.x, closest_position.y) <= BOAT_COLLISION_RADIUS


def velocity_units_per_second(boat: Boat) -> Vector2:
    speed_units_per_second = boat.speed_knots * COURSE_UNITS_PER_NAUTICAL_MILE / 3600.0
    radians = math.radians(boat.heading_degrees)
    return Vector2(
        math.sin(radians) * speed_units_per_second,
        -math.cos(radians) * speed_units_per_second,
    )


def ai_tactical_value(boat: Boat, salt: str) -> float:
    key = f"{boat.name}:{boat.target_leg_index}:{salt}"
    seed = 2166136261
    for character in key:
        seed ^= ord(character)
        seed = (seed * 16777619) & 0xFFFFFFFF
    return (seed / 0xFFFFFFFF) * 2.0 - 1.0


def ai_leg_mode(wind_direction: float, target_bearing: float) -> str:
    relative_to_wind = abs(signed_angle(wind_direction, target_bearing))
    if 50.0 <= relative_to_wind <= 130.0:
        return "reach"
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
    preference = board * ai_tactical_value(boat, f"{leg_mode}-board") * AI_TACTICAL_SCORE_BIAS
    return speed * alignment + preference - ai_mark_obstacle_penalty(boat, scenario, target_position, heading)


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

    if boat.penalty_turn_remaining_degrees > 0.0:
        step_penalty_turn(boat, elapsed_seconds)
        append_track_point(boat)
        return

    if boat.collision_stop_heading is not None:
        if headings_match(boat.heading_degrees, boat.collision_stop_heading):
            boat.speed_knots = 0.0
            append_track_point(boat)
            return
        boat.collision_stop_heading = None

    step_manual_maneuver(boat, elapsed_seconds)

    wind_direction, wind_speed = wind_at(scenario, boat.position)
    target_speed = target_boat_speed(
        scenario.polar,
        wind_speed,
        true_wind_angle(boat.heading_degrees, wind_direction),
    )
    if boat.maneuver_remaining_degrees > 0.0:
        target_speed *= boat.maneuver_speed_factor

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
    if (
        boat.control_mode == BoatControlMode.AI
        and not boat.has_started
        and scenario.race_state.elapsed_seconds < 0.0
        and start_finish_line_crossing_parameter(scenario, boat.position, next_position) is not None
    ):
        boat.speed_knots = 0.0
        append_track_point(boat)
        return

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


def tack(boat: Boat, wind_from_degrees: float, gradual: bool = False) -> None:
    difference = signed_angle(wind_from_degrees, boat.heading_degrees)
    turn = 90.0 if difference > 0 else -90.0
    if gradual:
        start_manual_maneuver(
            boat,
            turn,
            USER_TACK_TURN_RATE_DEGREES_PER_SECOND,
            USER_TACK_INITIAL_SPEED_FACTOR,
            USER_TACK_TARGET_SPEED_FACTOR,
        )
        return

    boat.heading_degrees = normalize_degrees(boat.heading_degrees + turn)
    boat.speed_knots *= 0.65
    release_collision_stop_if_heading_changed(boat)


def gybe(boat: Boat, wind_from_degrees: float, gradual: bool = False) -> None:
    difference = signed_angle(wind_from_degrees, boat.heading_degrees)
    turn = -90.0 if difference > 0 else 90.0
    if gradual:
        start_manual_maneuver(
            boat,
            turn,
            USER_GYBE_TURN_RATE_DEGREES_PER_SECOND,
            USER_GYBE_INITIAL_SPEED_FACTOR,
            USER_GYBE_TARGET_SPEED_FACTOR,
        )
        return

    boat.heading_degrees = normalize_degrees(boat.heading_degrees + turn)
    boat.speed_knots *= 0.75
    release_collision_stop_if_heading_changed(boat)


def start_manual_maneuver(
    boat: Boat,
    turn_degrees: float,
    turn_rate_degrees_per_second: float,
    initial_speed_factor: float,
    target_speed_factor: float,
) -> None:
    if boat.maneuver_remaining_degrees > 0.0:
        return

    boat.maneuver_remaining_degrees = abs(turn_degrees)
    boat.maneuver_turn_direction = 1 if turn_degrees >= 0.0 else -1
    boat.maneuver_turn_rate_degrees_per_second = turn_rate_degrees_per_second
    boat.maneuver_speed_factor = target_speed_factor
    boat.speed_knots *= initial_speed_factor
    release_collision_stop_if_heading_changed(boat)


def step_manual_maneuver(boat: Boat, elapsed_seconds: float) -> None:
    if boat.maneuver_remaining_degrees <= 0.0:
        boat.maneuver_remaining_degrees = 0.0
        boat.maneuver_speed_factor = 1.0
        return

    turn = min(boat.maneuver_remaining_degrees, boat.maneuver_turn_rate_degrees_per_second * elapsed_seconds)
    boat.heading_degrees = normalize_degrees(boat.heading_degrees + boat.maneuver_turn_direction * turn)
    boat.maneuver_remaining_degrees -= turn
    if boat.maneuver_remaining_degrees <= 1e-9:
        boat.maneuver_remaining_degrees = 0.0
        boat.maneuver_speed_factor = 1.0
        boat.maneuver_turn_rate_degrees_per_second = 0.0


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
        boat.mark_approach_target_leg_index = -1
        boat.collision_stop_heading = None
        boat.collision_released_heading = None
        boat.ai_board = None
        boat.ai_board_target_leg_index = -1
        boat.ai_last_maneuver_seconds = -9999.0
        boat.ai_rounding_target_leg_index = -1
        boat.ai_rounding_stage = 0
        boat.ai_collision_escape_until_seconds = 0.0
        boat.ai_collision_escape_heading = None
        boat.is_early_start = False
        boat.ai_start_strategy = None
        boat.penalty_turn_remaining_degrees = 0.0
        boat.penalty_resume_heading = None
        boat.penalty_turn_direction = 1
        boat.penalty_turns_owed = 0
        boat.penalty_clear_position = None
        boat.penalties_taken = 0
        boat.mark_touch_penalty_target_leg_index = -1
        boat.maneuver_remaining_degrees = 0.0
        boat.maneuver_turn_direction = 1
        boat.maneuver_turn_rate_degrees_per_second = 0.0
        boat.maneuver_speed_factor = 1.0
    scenario.race_state.elapsed_seconds = 0.0
    scenario.race_state.events = []
    scenario.race_state.finished_boats = set()


def start_race_sequence(scenario: Scenario) -> None:
    if (
        not scenario.race_state.is_running
        and scenario.race_state.elapsed_seconds == 0.0
        and all(not boat.has_started for boat in scenario.boats)
    ):
        scenario.race_state.elapsed_seconds = -max(0.0, scenario.race_state.start_sequence_seconds)
    scenario.race_state.is_running = True


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
                if scenario.race_state.elapsed_seconds < 0.0:
                    if not boat.is_early_start:
                        boat.is_early_start = True
                        add_event(
                            scenario,
                            RaceEventType.EARLY_START,
                            f"{boat.name} was over early.",
                        )
                    break

                boat.has_started = True
                boat.is_early_start = False
                segment_position = crossing
                add_event(scenario, RaceEventType.START_CROSSED, f"{boat.name} started.")
                continue

            target = target_mark_for(scenario.course, boat.target_leg_index)
            if target is not None:
                update_mark_approach_confirmation(scenario, boat, boat.target_leg_index, previous, boat.position)
                rounding = mark_rounding_parameter(
                    scenario,
                    boat.target_leg_index,
                    previous,
                    boat.position,
                    boat.mark_approach_target_leg_index == boat.target_leg_index,
                )
                if rounding is None or rounding + 1e-9 < segment_position:
                    break

                boat.target_leg_index += 1
                boat.mark_approach_target_leg_index = -1
                boat.ai_rounding_target_leg_index = -1
                boat.ai_rounding_stage = 0
                boat.mark_touch_penalty_target_leg_index = -1
                segment_position = rounding
                add_event(
                    scenario,
                    RaceEventType.MARK_ROUNDED,
                    f"{boat.name} rounded {target.label}.",
                )
                continue

            crossing = finish_line_crossing_parameter(scenario, previous, boat.position)
            crossing = earliest_valid_parameter([crossing], segment_position)
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
        update_mark_approach_confirmation(scenario, boat, boat.target_leg_index, previous, boat.position)
        if (
            mark_rounding_parameter(
                scenario,
                boat.target_leg_index,
                previous,
                boat.position,
                boat.mark_approach_target_leg_index == boat.target_leg_index,
            )
            is not None
        ):
            boat.target_leg_index += 1
            boat.mark_approach_target_leg_index = -1
            boat.ai_rounding_target_leg_index = -1
            boat.ai_rounding_stage = 0
            boat.mark_touch_penalty_target_leg_index = -1
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
            if boat_has_penalty_flag(first) or boat_has_penalty_flag(second):
                continue
            if apply_mark_room_collision_rule(first, second, scenario):
                continue
            if apply_port_starboard_collision_rule(first, second, scenario):
                continue
            if apply_same_tack_windward_leeward_collision_rule(first, second, scenario):
                continue
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


def boat_has_penalty_flag(boat: Boat) -> bool:
    return boat.penalty_turns_owed > 0 or boat.penalty_turn_remaining_degrees > 0.0


def detect_mark_collisions(scenario: Scenario) -> None:
    for boat in scenario.boats:
        target = target_mark_for(scenario.course, boat.target_leg_index)
        if target is None:
            continue
        if distance(boat.position, target.position) <= MARK_COLLISION_RADIUS:
            if boat.mark_touch_penalty_target_leg_index == boat.target_leg_index:
                continue
            if not start_mark_touch_penalty(boat):
                continue
            boat.mark_touch_penalty_target_leg_index = boat.target_leg_index
            boat.mark_approach_target_leg_index = -1
            boat.ai_rounding_target_leg_index = -1
            boat.ai_rounding_stage = 0
            add_event(
                scenario,
                RaceEventType.MARK_COLLISION,
                f"{boat.name} hit mark {target.label} and is taking a one-turn penalty.",
            )


def add_event(scenario: Scenario, event_type: RaceEventType, message: str) -> None:
    scenario.race_state.events.append(
        RaceEvent(
            event_type=event_type,
            message=message,
            elapsed_seconds=scenario.race_state.elapsed_seconds,
        )
    )


def apply_port_starboard_collision_rule(first: Boat, second: Boat, scenario: Scenario) -> bool:
    if not first.has_started or not second.has_started:
        return False
    if not boats_are_on_upwind_leg(first, second, scenario):
        return False

    first_tack = tack_side(first, scenario)
    second_tack = tack_side(second, scenario)
    if {first_tack, second_tack} != {"port", "starboard"}:
        return False

    port_boat = first if first_tack == "port" else second
    starboard_boat = second if port_boat is first else first
    start_penalty_turn(port_boat, starboard_boat)
    add_event(
        scenario,
        RaceEventType.RULE_PENALTY,
        f"{port_boat.name} fouled {starboard_boat.name} on starboard and is taking a two-turn penalty.",
    )
    return True


def apply_mark_room_collision_rule(first: Boat, second: Boat, scenario: Scenario) -> bool:
    keep_clear = mark_room_keep_clear_boat(first, second, scenario)
    if keep_clear is None:
        return False

    entitled = second if keep_clear is first else first
    start_penalty_turn(keep_clear, entitled)
    add_event(
        scenario,
        RaceEventType.RULE_PENALTY,
        f"{keep_clear.name} failed to give {entitled.name} mark-room and is taking a two-turn penalty.",
    )
    return True


def apply_same_tack_windward_leeward_collision_rule(first: Boat, second: Boat, scenario: Scenario) -> bool:
    if not first.has_started or not second.has_started:
        return False
    if tack_side(first, scenario) != tack_side(second, scenario):
        return False

    windward = windward_boat(first, second, scenario)
    leeward = second if windward is first else first
    start_penalty_turn(windward, leeward)
    add_event(
        scenario,
        RaceEventType.RULE_PENALTY,
        f"{windward.name} fouled {leeward.name} to leeward and is taking a two-turn penalty.",
    )
    return True


def boats_are_on_upwind_leg(first: Boat, second: Boat, scenario: Scenario) -> bool:
    return boat_is_on_upwind_leg(first, scenario) and boat_is_on_upwind_leg(second, scenario)


def boat_is_on_upwind_leg(boat: Boat, scenario: Scenario) -> bool:
    target = target_mark_for(scenario.course, boat.target_leg_index)
    if target is not None:
        return target.mark_type == MarkType.WINDWARD

    from sailing_simulator.domain.wind import wind_at

    wind_direction, _ = wind_at(scenario, boat.position)
    return true_wind_angle(boat.heading_degrees, wind_direction) <= 100.0


def tack_side(boat: Boat, scenario: Scenario) -> str:
    from sailing_simulator.domain.wind import wind_at

    wind_direction, _ = wind_at(scenario, boat.position)
    return "starboard" if signed_angle(wind_direction, boat.heading_degrees) > 0.0 else "port"


def windward_boat(first: Boat, second: Boat, scenario: Scenario) -> Boat:
    leeward = leeward_boat(first, second, scenario)
    return second if leeward is first else first


def leeward_boat(first: Boat, second: Boat, scenario: Scenario) -> Boat:
    from sailing_simulator.domain.wind import wind_at

    wind_direction, _ = wind_at(scenario, midpoint(first.position, second.position))
    radians = math.radians(wind_direction)
    downwind_unit = Vector2(-math.sin(radians), math.cos(radians))
    first_downwind = dot(first.position, downwind_unit)
    second_downwind = dot(second.position, downwind_unit)
    return first if first_downwind >= second_downwind else second


def midpoint_heading(first_heading: float, second_heading: float) -> float:
    return normalize_degrees(first_heading + signed_angle(second_heading, first_heading) * 0.5)


def heading_unit(heading: float) -> Vector2:
    radians = math.radians(heading)
    return Vector2(math.sin(radians), -math.cos(radians))


def midpoint(first: Vector2, second: Vector2) -> Vector2:
    return Vector2((first.x + second.x) / 2.0, (first.y + second.y) / 2.0)


def start_penalty_turn(port_boat: Boat, starboard_boat: Boat) -> None:
    turn_direction = -1 if signed_angle(starboard_boat.heading_degrees, port_boat.heading_degrees) < 0.0 else 1
    queue_penalty_turns(port_boat, 2, port_boat.position, turn_direction)


def start_mark_touch_penalty(boat: Boat) -> bool:
    if boat.penalty_turn_remaining_degrees > 0.0 or boat.penalty_turns_owed > 0:
        return False

    queue_penalty_turns(boat, 1, boat.position, 1)
    return True


def queue_penalty_turns(boat: Boat, turns: int, clear_position: Vector2, turn_direction: int) -> None:
    if turns <= 0:
        return

    boat.penalty_turns_owed += turns
    boat.penalty_clear_position = clear_position
    boat.penalty_turn_direction = turn_direction
    boat.penalties_taken += 1
    boat.collision_stop_heading = None
    boat.collision_released_heading = None


def start_penalty_turn_if_owed(boat: Boat) -> bool:
    if boat.penalty_turns_owed <= 0 or boat.penalty_turn_remaining_degrees > 0.0:
        return False

    boat.penalty_turns_owed -= 1
    boat.penalty_resume_heading = boat.heading_degrees
    boat.penalty_turn_remaining_degrees = PENALTY_TURN_DEGREES_PER_TURN
    boat.speed_knots = 0.0
    boat.collision_stop_heading = None
    boat.collision_released_heading = None
    return True


def ai_boat_is_clear_for_penalty(boat: Boat) -> bool:
    if boat.penalty_clear_position is None:
        return True
    return distance(boat.position, boat.penalty_clear_position) >= AI_PENALTY_CLEAR_DISTANCE


def step_penalty_turn(boat: Boat, elapsed_seconds: float) -> None:
    turn = min(boat.penalty_turn_remaining_degrees, PENALTY_TURN_RATE_DEGREES_PER_SECOND * elapsed_seconds)
    boat.heading_degrees = normalize_degrees(boat.heading_degrees + boat.penalty_turn_direction * turn)
    boat.penalty_turn_remaining_degrees -= turn
    boat.speed_knots = 0.0
    if boat.penalty_turn_remaining_degrees <= 1e-9:
        boat.penalty_turn_remaining_degrees = 0.0
        if boat.penalty_resume_heading is not None:
            boat.heading_degrees = normalize_degrees(boat.penalty_resume_heading)
        boat.penalty_resume_heading = None
        if boat.penalty_turns_owed <= 0:
            boat.penalty_clear_position = None


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
    approach_confirmed: bool = True,
) -> float | None:
    target = target_mark_for(scenario.course, target_leg_index)
    if target is None:
        return None

    side_unit = rounding_boat_side_unit(scenario, target_leg_index)
    gate_unit = mark_rounding_gate_unit_for(scenario, target_leg_index)
    if side_unit is None or gate_unit is None:
        return mark_crossing_parameter(target.position, segment_start, segment_end, MARK_COLLISION_RADIUS)
    if not approach_confirmed:
        return None

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


def update_mark_approach_confirmation(
    scenario: Scenario,
    boat: Boat,
    target_leg_index: int,
    segment_start: Vector2,
    segment_end: Vector2,
) -> None:
    if boat.mark_approach_target_leg_index == target_leg_index:
        return

    incoming_unit = incoming_leg_unit_for(scenario, target_leg_index)
    target = target_mark_for(scenario.course, target_leg_index)
    if incoming_unit is None or target is None:
        return

    start_progress = dot(Vector2(segment_start.x - target.position.x, segment_start.y - target.position.y), incoming_unit)
    end_progress = dot(Vector2(segment_end.x - target.position.x, segment_end.y - target.position.y), incoming_unit)
    if max(start_progress, end_progress) >= MARK_APPROACH_CONFIRM_DISTANCE:
        boat.mark_approach_target_leg_index = target_leg_index


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


def prestart_side_unit(scenario: Scenario) -> Vector2:
    start = scenario.course.start_line
    dx = start.committee_boat.x - start.pin.x
    dy = start.committee_boat.y - start.pin.y
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return Vector2(0.0, 1.0)

    first_target = first_ai_target_position(scenario)
    center = start_line_center(scenario)
    first_normal = Vector2(-dy / length, dx / length)
    second_normal = Vector2(dy / length, -dx / length)
    toward_course = Vector2(first_target.x - center.x, first_target.y - center.y)
    return second_normal if dot(toward_course, first_normal) >= dot(toward_course, second_normal) else first_normal


def start_finish_line_crossing_parameter(scenario: Scenario, segment_start: Vector2, segment_end: Vector2) -> float | None:
    line_start, line_end = extended_start_finish_line(scenario)
    crossing = segment_intersection_parameter(segment_start, segment_end, line_start, line_end)
    if crossing is not None:
        return crossing
    if distance_from_segment(segment_end, line_start, line_end) <= START_FINISH_LINE_TOUCH_RADIUS:
        return 1.0
    return None


def finish_line_crossing_parameter(scenario: Scenario, segment_start: Vector2, segment_end: Vector2) -> float | None:
    line_start, line_end = actual_start_finish_line(scenario)
    return segment_intersection_parameter(segment_start, segment_end, line_start, line_end)


def actual_start_finish_line(scenario: Scenario) -> tuple[Vector2, Vector2]:
    start = scenario.course.start_line
    return start.pin, start.committee_boat


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
