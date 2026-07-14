from sailing_simulator.domain.models import (
    BoatControlMode,
    MarkType,
    RaceEventType,
    RaceFormat,
    StartLine,
    Vector2,
    default_scenario,
)
from sailing_simulator.domain.presets import course_for_format
from sailing_simulator.domain.simulation import (
    AI_COLLISION_ESCAPE_MAX_SECONDS,
    AI_COLLISION_ESCAPE_MIN_SECONDS,
    AI_MIN_MANEUVER_INTERVAL_SECONDS,
    ai_board_heading,
    ai_board_near_boundary,
    ai_prestart_target_position_for_boat,
    ai_start_strategy_for_boat,
    ai_steering_target_position,
    ai_target_position,
    bearing_to,
    best_vmg_heading,
    collision_avoidance_maneuver,
    detect_race_events,
    gybe,
    reset_boats_to_start,
    start_race_sequence,
    step_boat,
    step_scenario,
    steer_away_from_wind,
    should_tack_to_avoid_collision,
    tack,
    target_boat_speed,
    true_wind_angle,
    turn_toward_heading,
    update_ai_heading,
)


def test_true_wind_angle_is_absolute_angle_to_wind_source():
    assert true_wind_angle(45.0, 0.0) == 45.0
    assert true_wind_angle(315.0, 0.0) == 45.0
    assert true_wind_angle(180.0, 0.0) == 180.0


def test_polar_lookup_interpolates_between_wind_speeds_and_angles():
    scenario = default_scenario()

    speed = target_boat_speed(scenario.polar, 8.0, 75.0)

    assert round(speed, 2) == 5.3


def test_no_go_zone_slows_boat_inside_45_degrees():
    scenario = default_scenario()

    speed_at_45 = target_boat_speed(scenario.polar, 10.0, 45.0)
    speed_at_20 = target_boat_speed(scenario.polar, 10.0, 20.0)

    assert speed_at_20 < speed_at_45


def test_step_scenario_moves_user_boat_and_records_track():
    scenario = default_scenario()
    boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.USER)
    starting_position = boat.position

    step_scenario(scenario, 5.0)

    assert boat.position != starting_position
    assert boat.speed_knots > 0.0
    assert boat.track


def test_tack_turns_boat_roughly_onto_opposite_tack_and_slows():
    scenario = default_scenario()
    boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.USER)
    boat.speed_knots = 5.0

    tack(boat, scenario.wind_model.base_direction_degrees)

    assert boat.heading_degrees == 45.0
    assert boat.speed_knots == 3.25


def test_gybe_turns_boat_roughly_onto_opposite_downwind_board_and_slows():
    scenario = default_scenario()
    boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.USER)
    boat.heading_degrees = 145.0
    boat.speed_knots = 6.0

    gybe(boat, scenario.wind_model.base_direction_degrees)

    assert boat.heading_degrees == 235.0
    assert boat.speed_knots == 4.5


def test_gybe_turns_opposite_direction_from_other_downwind_board():
    scenario = default_scenario()
    boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.USER)
    boat.heading_degrees = 215.0

    gybe(boat, scenario.wind_model.base_direction_degrees)

    assert boat.heading_degrees == 125.0


def test_ai_boat_moves_under_simulation():
    scenario = default_scenario()
    ai_boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.AI)
    starting_position = ai_boat.position

    step_scenario(scenario, 5.0)

    assert ai_boat.position != starting_position
    assert ai_boat.speed_knots > 0.0


def test_finished_boat_stays_stopped():
    scenario = default_scenario()
    boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.USER)
    boat.is_finished = True
    boat.speed_knots = 8.0
    starting_position = boat.position

    step_scenario(scenario, 5.0)

    assert boat.position == starting_position
    assert boat.speed_knots == 0.0


def test_best_vmg_heading_points_generally_toward_target():
    scenario = default_scenario()
    ai_boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.AI)
    target = scenario.course.marks[0].position

    heading = best_vmg_heading(ai_boat, scenario, target)
    target_bearing = bearing_to(ai_boat.position, target)

    assert abs((heading - target_bearing + 180.0) % 360.0 - 180.0) <= 70.0


def test_ai_holds_board_between_maneuver_decisions():
    scenario = default_scenario()
    ai_boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.AI)

    step_scenario(scenario, 1.0)
    first_board = ai_boat.ai_board
    first_heading = ai_boat.heading_degrees
    step_scenario(scenario, 1.0)

    assert ai_boat.ai_board == first_board
    assert ai_boat.heading_degrees == turn_toward_heading(first_heading, ai_board_heading(0.0, "upwind", first_board), 18.0)


def test_ai_changes_board_near_boundary_after_cooldown():
    scenario = default_scenario()
    ai_boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.AI)
    ai_boat.position = Vector2(scenario.course.boundary_width - 20.0, 500.0)
    ai_boat.ai_board = 1
    ai_boat.ai_board_target_leg_index = ai_boat.target_leg_index
    ai_boat.ai_last_maneuver_seconds = 0.0
    scenario.race_state.elapsed_seconds = AI_MIN_MANEUVER_INTERVAL_SECONDS + 1.0

    assert ai_board_near_boundary(ai_boat, scenario, 0.0, "upwind")
    step_scenario(scenario, 1.0)

    assert ai_boat.ai_board == -1


def test_ai_targets_start_finish_line_after_w_course_marks_are_complete():
    scenario = default_scenario()
    ai_boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.AI)
    ai_boat.has_started = True
    ai_boat.target_leg_index = 2
    ai_boat.ai_board = 1

    assert ai_target_position(ai_boat, scenario) == Vector2(555.0, 700.0)


def test_ai_targets_prestart_side_during_countdown():
    scenario = default_scenario()
    scenario.race_state.elapsed_seconds = -60.0
    ai_boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.AI)

    target = ai_target_position(ai_boat, scenario)
    prestart_target = ai_prestart_target_position_for_boat(ai_boat, scenario)

    assert target == prestart_target
    assert target.y > scenario.course.start_line.pin.y


def test_ai_prestart_targets_move_along_line_over_time():
    scenario = default_scenario()
    ai_boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.AI)

    scenario.race_state.elapsed_seconds = -60.0
    first_target = ai_prestart_target_position_for_boat(ai_boat, scenario)
    scenario.race_state.elapsed_seconds = -45.0
    second_target = ai_prestart_target_position_for_boat(ai_boat, scenario)

    assert first_target.y == second_target.y
    assert first_target.x != second_target.x


def test_ai_boats_use_different_start_strategies():
    scenario = default_scenario()
    ai_boats = [boat for boat in scenario.boats if boat.control_mode == BoatControlMode.AI]

    strategies = [ai_start_strategy_for_boat(boat, scenario) for boat in ai_boats]

    assert strategies == ["middle", "committee"]


def test_ai_targets_leeward_mark_before_w2_finish_line():
    scenario = default_scenario()
    ai_boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.AI)
    ai_boat.has_started = True
    ai_boat.target_leg_index = 1
    leeward = next(mark for mark in scenario.course.marks if mark.mark_type == MarkType.LEEWARD)

    assert ai_target_position(ai_boat, scenario) == leeward.position


def test_ai_uses_staged_leeward_rounding_waypoints():
    scenario = default_scenario()
    ai_boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.AI)
    ai_boat.has_started = True
    ai_boat.target_leg_index = 1
    leeward = next(mark for mark in scenario.course.marks if mark.mark_type == MarkType.LEEWARD)
    leeward.position = Vector2(460.0, 720.0)

    ai_boat.position = Vector2(380.0, 650.0)
    approach_target = ai_steering_target_position(ai_boat, scenario)
    assert approach_target.y > leeward.position.y
    assert approach_target.x < leeward.position.x
    assert ai_boat.ai_rounding_stage == 0

    ai_boat.position = approach_target
    wrap_target = ai_steering_target_position(ai_boat, scenario)
    assert wrap_target.y > leeward.position.y
    assert wrap_target.x > leeward.position.x
    assert ai_boat.ai_rounding_stage == 1

    ai_boat.position = wrap_target
    exit_target = ai_steering_target_position(ai_boat, scenario)
    assert exit_target.y < leeward.position.y
    assert exit_target.x > leeward.position.x
    assert ai_boat.ai_rounding_stage == 2


def test_ai_targets_t3_leeward_mark_before_finish_line():
    scenario = default_scenario()
    scenario.course = course_for_format(RaceFormat.T3)
    ai_boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.AI)
    leeward = next(mark for mark in scenario.course.marks if mark.mark_type == MarkType.LEEWARD)
    ai_boat.has_started = True
    ai_boat.target_leg_index = 2

    assert ai_target_position(ai_boat, scenario) == leeward.position


def test_ai_targets_t3_start_finish_line_after_required_marks_are_complete():
    scenario = default_scenario()
    scenario.course = course_for_format(RaceFormat.T3)
    ai_boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.AI)
    ai_boat.has_started = True
    ai_boat.target_leg_index = 3

    assert ai_target_position(ai_boat, scenario) == Vector2(555.0, 700.0)


def test_ai_steers_directly_on_reaching_leg():
    scenario = default_scenario()
    scenario.course = course_for_format(RaceFormat.T3)
    ai_boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.AI)
    gybe = next(mark for mark in scenario.course.marks if mark.mark_type == MarkType.GYBE)
    ai_boat.has_started = True
    ai_boat.target_leg_index = 1
    ai_boat.position = Vector2(gybe.position.x + 220.0, gybe.position.y)
    ai_boat.heading_degrees = 90.0

    step_scenario(scenario, 1.0)

    assert ai_boat.heading_degrees > 90.0


def test_ai_fleet_completes_t3_course():
    scenario = default_scenario()
    scenario.course = course_for_format(RaceFormat.T3)
    reset_boats_to_start(scenario)

    for _ in range(2500):
        step_scenario(scenario, 1.0)

    ai_boats = [boat for boat in scenario.boats if boat.control_mode == BoatControlMode.AI]
    assert all(boat.target_leg_index == 3 for boat in ai_boats)
    assert all(boat.is_finished for boat in ai_boats)


def test_default_ai_fleet_rounds_and_finishes_without_hitting_marks():
    scenario = default_scenario()

    for _ in range(1800):
        step_scenario(scenario, 1.0)

    ai_boats = [boat for boat in scenario.boats if boat.control_mode == BoatControlMode.AI]
    assert all(boat.target_leg_index == 2 for boat in ai_boats)
    assert all(boat.is_finished for boat in ai_boats)


def test_ai_fleet_completes_w2_with_mid_course_finish_line():
    scenario = default_scenario()
    scenario.course.start_line = StartLine(pin=Vector2(320.0, 620.0), committee_boat=Vector2(545.0, 620.0))
    for mark in scenario.course.marks:
        if mark.mark_type == MarkType.WINDWARD:
            mark.position = Vector2(430.0, 220.0)
        if mark.mark_type == MarkType.LEEWARD:
            mark.position = Vector2(432.0, 840.0)
    reset_boats_to_start(scenario)

    for _ in range(1800):
        step_scenario(scenario, 1.0)

    ai_boats = [boat for boat in scenario.boats if boat.control_mode == BoatControlMode.AI]
    assert all(boat.target_leg_index == 2 for boat in ai_boats)
    assert all(boat.is_finished for boat in ai_boats)


def test_turn_toward_heading_uses_shortest_turn():
    assert turn_toward_heading(315.0, 0.0, 18.0) == 333.0
    assert turn_toward_heading(45.0, 0.0, 18.0) == 27.0


def test_line_crossing_starts_before_it_can_finish():
    scenario = default_scenario()
    boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.USER)
    previous = Vector2(450.0, 710.0)
    boat.position = Vector2(450.0, 690.0)

    detect_race_events(scenario, {boat.name: previous})
    detect_race_events(scenario, {boat.name: previous})

    assert boat.has_started
    assert boat.name not in scenario.race_state.finished_boats
    assert [event.event_type for event in scenario.race_state.events].count(RaceEventType.START_CROSSED) == 1


def test_start_sequence_counts_down_to_race_time_zero():
    scenario = default_scenario()
    scenario.race_state.start_sequence_seconds = 30.0

    start_race_sequence(scenario)

    assert scenario.race_state.is_running
    assert scenario.race_state.elapsed_seconds == -30.0

    step_scenario(scenario, 10.0)

    assert scenario.race_state.elapsed_seconds == -20.0

    step_scenario(scenario, 20.0)

    assert scenario.race_state.elapsed_seconds == 0.0


def test_paused_start_sequence_resumes_without_resetting_countdown():
    scenario = default_scenario()
    scenario.race_state.start_sequence_seconds = 30.0

    start_race_sequence(scenario)
    step_scenario(scenario, 10.0)
    scenario.race_state.is_running = False
    start_race_sequence(scenario)

    assert scenario.race_state.elapsed_seconds == -20.0
    assert scenario.race_state.is_running


def test_line_crossing_before_start_is_recorded_as_early_start_not_valid_start():
    scenario = default_scenario()
    scenario.race_state.elapsed_seconds = -5.0
    boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.USER)
    previous = Vector2(450.0, 710.0)
    boat.position = Vector2(450.0, 690.0)

    detect_race_events(scenario, {boat.name: previous})

    assert boat.is_early_start
    assert not boat.has_started
    assert any(event.event_type == RaceEventType.EARLY_START for event in scenario.race_state.events)


def test_ai_boat_does_not_cross_start_line_before_countdown_reaches_zero():
    scenario = default_scenario()
    ai_boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.AI)
    scenario.boats = [ai_boat]
    scenario.race_state.elapsed_seconds = -5.0
    ai_boat.position = Vector2(450.0, 710.0)
    ai_boat.heading_degrees = 0.0
    ai_boat.speed_knots = 8.0

    step_boat(ai_boat, scenario, 5.0)

    assert ai_boat.position == Vector2(450.0, 710.0)
    assert ai_boat.speed_knots == 0.0
    assert not ai_boat.is_early_start
    assert not any(event.event_type == RaceEventType.EARLY_START for event in scenario.race_state.events)


def test_early_start_boat_must_cross_again_after_gun():
    scenario = default_scenario()
    boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.USER)
    scenario.race_state.elapsed_seconds = -1.0
    previous = Vector2(450.0, 710.0)
    boat.position = Vector2(450.0, 690.0)

    detect_race_events(scenario, {boat.name: previous})
    scenario.race_state.elapsed_seconds = 0.5
    previous = Vector2(450.0, 690.0)
    boat.position = Vector2(450.0, 710.0)

    detect_race_events(scenario, {boat.name: previous})

    assert boat.has_started
    assert not boat.is_early_start
    assert any(event.event_type == RaceEventType.START_CROSSED for event in scenario.race_state.events)


def test_mark_rounding_advances_target_leg():
    scenario = default_scenario()
    boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.USER)
    boat.has_started = True
    windward = next(mark for mark in scenario.course.marks if mark.mark_type == MarkType.WINDWARD)
    previous = Vector2(windward.position.x - 40.0, windward.position.y + 20.0)
    boat.position = Vector2(windward.position.x - 40.0, windward.position.y - 20.0)

    detect_race_events(scenario, {boat.name: previous})

    assert boat.target_leg_index == 1
    assert any(event.event_type == RaceEventType.MARK_ROUNDED for event in scenario.race_state.events)


def test_touching_mark_without_passing_rounding_gate_does_not_advance_leg():
    scenario = default_scenario()
    boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.USER)
    boat.has_started = True
    windward = next(mark for mark in scenario.course.marks if mark.mark_type == MarkType.WINDWARD)
    boat.position = windward.position

    detect_race_events(scenario, {boat.name: boat.position})

    assert boat.target_leg_index == 0
    assert any(event.event_type == RaceEventType.MARK_COLLISION for event in scenario.race_state.events)
    assert not any(event.event_type == RaceEventType.MARK_ROUNDED for event in scenario.race_state.events)


def test_starboard_rounding_side_does_not_advance_leg():
    scenario = default_scenario()
    boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.USER)
    boat.has_started = True
    windward = next(mark for mark in scenario.course.marks if mark.mark_type == MarkType.WINDWARD)
    previous = Vector2(windward.position.x + 40.0, windward.position.y + 20.0)
    boat.position = Vector2(windward.position.x + 40.0, windward.position.y - 20.0)

    detect_race_events(scenario, {boat.name: previous})

    assert boat.target_leg_index == 0
    assert not any(event.event_type == RaceEventType.MARK_ROUNDED for event in scenario.race_state.events)


def test_mark_rounding_advances_when_boat_passes_through_mark_radius_between_ticks():
    scenario = default_scenario()
    boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.USER)
    boat.has_started = True
    windward = next(mark for mark in scenario.course.marks if mark.mark_type == MarkType.WINDWARD)
    previous = Vector2(windward.position.x - 40.0, windward.position.y + 80.0)
    boat.position = Vector2(windward.position.x - 40.0, windward.position.y - 80.0)

    detect_race_events(scenario, {boat.name: previous})

    assert boat.target_leg_index == 1
    assert any(event.event_type == RaceEventType.MARK_ROUNDED for event in scenario.race_state.events)


def test_leeward_port_rounding_requires_upwind_exit():
    scenario = default_scenario()
    scenario.course = course_for_format(RaceFormat.W4)
    boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.USER)
    boat.has_started = True
    boat.target_leg_index = 1
    leeward = next(mark for mark in scenario.course.marks if mark.mark_type == MarkType.LEEWARD)
    previous = Vector2(leeward.position.x + 40.0, leeward.position.y + 20.0)
    boat.position = Vector2(leeward.position.x + 40.0, leeward.position.y - 20.0)

    detect_race_events(scenario, {boat.name: previous})

    assert boat.target_leg_index == 2
    assert any(event.event_type == RaceEventType.MARK_ROUNDED for event in scenario.race_state.events)


def test_leeward_downwind_exit_does_not_round():
    scenario = default_scenario()
    scenario.course = course_for_format(RaceFormat.W4)
    boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.USER)
    boat.has_started = True
    boat.target_leg_index = 1
    leeward = next(mark for mark in scenario.course.marks if mark.mark_type == MarkType.LEEWARD)
    previous = Vector2(leeward.position.x + 40.0, leeward.position.y - 20.0)
    boat.position = Vector2(leeward.position.x + 40.0, leeward.position.y + 20.0)

    detect_race_events(scenario, {boat.name: previous})

    assert boat.target_leg_index == 1
    assert not any(event.event_type == RaceEventType.MARK_ROUNDED for event in scenario.race_state.events)


def test_finish_crossing_only_counts_after_required_marks():
    scenario = default_scenario()
    boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.USER)
    boat.has_started = True
    boat.target_leg_index = 2
    previous = Vector2(450.0, 690.0)
    boat.position = Vector2(450.0, 710.0)

    detect_race_events(scenario, {boat.name: previous})

    assert boat.is_finished
    assert boat.name in scenario.race_state.finished_boats
    assert any(event.event_type == RaceEventType.FINISH_CROSSED for event in scenario.race_state.events)


def test_w2_does_not_finish_when_passing_line_before_leeward_mark():
    scenario = default_scenario()
    boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.USER)
    boat.has_started = True
    boat.target_leg_index = 1
    previous = Vector2(450.0, 690.0)
    boat.position = Vector2(450.0, 710.0)

    detect_race_events(scenario, {boat.name: previous})

    assert not boat.is_finished
    assert boat.target_leg_index == 1
    assert boat.name not in scenario.race_state.finished_boats
    assert not any(event.event_type == RaceEventType.FINISH_CROSSED for event in scenario.race_state.events)


def test_w2_does_not_round_deep_leeward_when_crossing_mid_course_line():
    scenario = default_scenario()
    scenario.course.start_line = StartLine(pin=Vector2(320.0, 700.0), committee_boat=Vector2(560.0, 700.0))
    leeward = next(mark for mark in scenario.course.marks if mark.mark_type == MarkType.LEEWARD)
    leeward.position = Vector2(430.0, 850.0)
    boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.USER)
    boat.has_started = True
    boat.target_leg_index = 1
    previous = Vector2(450.0, 690.0)
    boat.position = Vector2(450.0, 710.0)

    detect_race_events(scenario, {boat.name: previous})

    assert boat.target_leg_index == 1
    assert not boat.is_finished
    assert not any(event.event_type == RaceEventType.MARK_ROUNDED for event in scenario.race_state.events)
    assert not any(event.event_type == RaceEventType.FINISH_CROSSED for event in scenario.race_state.events)


def test_t3_does_not_finish_at_leeward_mark_before_start_finish_line():
    scenario = default_scenario()
    scenario.course = course_for_format(RaceFormat.T3)
    boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.USER)
    boat.has_started = True
    boat.target_leg_index = 2
    boat.mark_approach_target_leg_index = 2
    leeward = next(mark for mark in scenario.course.marks if mark.mark_type == MarkType.LEEWARD)
    previous = Vector2(leeward.position.x + 40.0, leeward.position.y + 20.0)
    boat.position = Vector2(leeward.position.x + 40.0, leeward.position.y - 20.0)

    detect_race_events(scenario, {boat.name: previous})

    assert boat.target_leg_index == 3
    assert not boat.is_finished
    assert boat.name not in scenario.race_state.finished_boats


def test_t3_finishes_on_start_finish_line_after_leeward_mark():
    scenario = default_scenario()
    scenario.course = course_for_format(RaceFormat.T3)
    boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.USER)
    boat.has_started = True
    boat.target_leg_index = 3
    previous = Vector2(450.0, 690.0)
    boat.position = Vector2(450.0, 710.0)

    detect_race_events(scenario, {boat.name: previous})

    assert boat.is_finished
    assert boat.name in scenario.race_state.finished_boats


def test_t3_does_not_finish_on_start_finish_line_before_leeward_mark():
    scenario = default_scenario()
    scenario.course = course_for_format(RaceFormat.T3)
    boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.USER)
    boat.has_started = True
    boat.target_leg_index = 2
    previous = Vector2(450.0, 690.0)
    boat.position = Vector2(450.0, 710.0)

    detect_race_events(scenario, {boat.name: previous})

    assert not boat.is_finished
    assert boat.target_leg_index == 2
    assert boat.name not in scenario.race_state.finished_boats


def test_w_course_does_not_finish_at_leeward_mark_before_sequence_complete():
    scenario = default_scenario()
    scenario.course = course_for_format(RaceFormat.W4)
    boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.USER)
    boat.has_started = True
    boat.target_leg_index = 1
    leeward = next(mark for mark in scenario.course.marks if mark.mark_type == MarkType.LEEWARD)
    previous = Vector2(leeward.position.x + 40.0, leeward.position.y + 20.0)
    boat.position = Vector2(leeward.position.x + 40.0, leeward.position.y - 20.0)

    detect_race_events(scenario, {boat.name: previous})

    assert boat.target_leg_index == 2
    assert not boat.is_finished
    assert boat.name not in scenario.race_state.finished_boats


def test_w_course_finishes_after_all_marks_and_start_line_crossing():
    scenario = default_scenario()
    scenario.course = course_for_format(RaceFormat.W4)
    boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.USER)
    boat.has_started = True
    boat.target_leg_index = 4
    previous = Vector2(450.0, 690.0)
    boat.position = Vector2(450.0, 710.0)

    detect_race_events(scenario, {boat.name: previous})

    assert boat.is_finished
    assert boat.name in scenario.race_state.finished_boats


def test_w_course_finish_counts_just_beyond_committee_end():
    scenario = default_scenario()
    boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.USER)
    boat.has_started = True
    boat.target_leg_index = 2
    previous = Vector2(585.0, 690.0)
    boat.position = Vector2(585.0, 710.0)

    detect_race_events(scenario, {boat.name: previous})

    assert boat.is_finished
    assert boat.name in scenario.race_state.finished_boats


def test_w_course_finish_counts_when_boat_reaches_line_band():
    scenario = default_scenario()
    boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.USER)
    boat.has_started = True
    boat.target_leg_index = 2
    previous = Vector2(450.0, 681.0)
    boat.position = Vector2(450.0, 686.0)

    detect_race_events(scenario, {boat.name: previous})

    assert boat.is_finished
    assert boat.name in scenario.race_state.finished_boats


def test_progress_can_round_last_mark_then_finish_on_line():
    scenario = default_scenario()
    boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.USER)
    scenario.boats = [boat]
    boat.has_started = True
    windward = next(mark for mark in scenario.course.marks if mark.mark_type == MarkType.WINDWARD)
    leeward = next(mark for mark in scenario.course.marks if mark.mark_type == MarkType.LEEWARD)

    previous = Vector2(windward.position.x - 40.0, windward.position.y + 20.0)
    boat.position = Vector2(windward.position.x - 40.0, windward.position.y - 20.0)
    detect_race_events(scenario, {boat.name: previous})

    assert boat.target_leg_index == 1
    assert not boat.is_finished

    previous = Vector2(leeward.position.x + 40.0, leeward.position.y + 20.0)
    boat.position = Vector2(leeward.position.x + 40.0, leeward.position.y - 20.0)
    detect_race_events(scenario, {boat.name: previous})

    assert boat.target_leg_index == 2
    assert boat.is_finished
    assert any(event.event_type == RaceEventType.FINISH_CROSSED for event in scenario.race_state.events)


def test_boat_collision_creates_event():
    scenario = default_scenario()
    scenario.boats[0].position = Vector2(400.0, 400.0)
    scenario.boats[1].position = Vector2(410.0, 400.0)

    detect_race_events(scenario, {})

    assert any(event.event_type == RaceEventType.BOAT_COLLISION for event in scenario.race_state.events)


def test_boat_collision_stops_both_boats_until_heading_changes():
    scenario = default_scenario()
    first, second = scenario.boats[0], scenario.boats[1]
    first.position = Vector2(400.0, 400.0)
    second.position = Vector2(410.0, 400.0)
    first.speed_knots = 5.0
    second.speed_knots = 4.0

    detect_race_events(scenario, {})

    assert first.speed_knots == 0.0
    assert second.speed_knots == 0.0
    assert first.collision_stop_heading == first.heading_degrees
    step_scenario(scenario, 1.0)
    assert first.speed_knots == 0.0

    steer_away_from_wind(first, scenario.wind_model.base_direction_degrees, 5.0)
    step_scenario(scenario, 1.0)

    assert first.collision_stop_heading is None


def test_port_boat_hitting_starboard_on_upwind_leg_takes_two_turn_penalty():
    scenario = default_scenario()
    port_boat, starboard_boat = scenario.boats[0], scenario.boats[1]
    port_boat.has_started = True
    starboard_boat.has_started = True
    port_boat.heading_degrees = 45.0
    starboard_boat.heading_degrees = 315.0
    port_boat.position = Vector2(420.0, 420.0)
    starboard_boat.position = Vector2(430.0, 420.0)
    port_boat.speed_knots = 5.0
    starboard_boat.speed_knots = 5.0

    detect_race_events(scenario, {})

    assert port_boat.penalty_turn_remaining_degrees == 720.0
    assert port_boat.penalty_resume_heading == 45.0
    assert port_boat.penalties_taken == 1
    assert port_boat.speed_knots == 0.0
    assert starboard_boat.speed_knots == 5.0
    assert starboard_boat.collision_stop_heading is None
    assert any(event.event_type == RaceEventType.RULE_PENALTY for event in scenario.race_state.events)
    assert not any(event.event_type == RaceEventType.BOAT_COLLISION for event in scenario.race_state.events)


def test_penalty_turn_resumes_original_heading_after_two_360s():
    scenario = default_scenario()
    boat = scenario.boats[0]
    boat.heading_degrees = 45.0
    boat.penalty_resume_heading = 45.0
    boat.penalty_turn_remaining_degrees = 720.0
    boat.penalty_turn_direction = 1

    step_boat(boat, scenario, 2.0)

    assert boat.heading_degrees == 225.0
    assert boat.penalty_turn_remaining_degrees == 540.0

    step_boat(boat, scenario, 6.0)

    assert boat.heading_degrees == 45.0
    assert boat.penalty_turn_remaining_degrees == 0.0
    assert boat.penalty_resume_heading is None


def test_ai_boat_taking_penalty_turn_does_not_steer_tactically_first():
    scenario = default_scenario()
    boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.AI)
    boat.heading_degrees = 45.0
    boat.penalty_resume_heading = 45.0
    boat.penalty_turn_remaining_degrees = 720.0
    boat.penalty_turn_direction = 1

    step_scenario(scenario, 1.0)

    assert boat.heading_degrees == 135.0
    assert boat.penalty_turn_remaining_degrees == 630.0


def test_ai_boat_tacks_before_projected_upwind_collision():
    scenario = default_scenario()
    ai_boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.AI)
    other_boat = scenario.boats[0]
    ai_boat.has_started = True
    other_boat.has_started = True
    ai_boat.position = Vector2(400.0, 400.0)
    other_boat.position = Vector2(435.0, 400.0)
    ai_boat.heading_degrees = 45.0
    other_boat.heading_degrees = 315.0
    ai_boat.speed_knots = 10.0
    other_boat.speed_knots = 10.0
    scenario.race_state.elapsed_seconds = 20.0

    update_ai_heading(ai_boat, scenario)

    assert ai_boat.heading_degrees == 315.0
    assert ai_boat.speed_knots == 6.5


def test_ai_boat_does_not_tack_before_projected_collision_outside_close_zone():
    scenario = default_scenario()
    ai_boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.AI)
    other_boat = scenario.boats[0]
    ai_boat.has_started = True
    other_boat.has_started = True
    ai_boat.position = Vector2(400.0, 400.0)
    other_boat.position = Vector2(470.0, 400.0)
    ai_boat.heading_degrees = 45.0
    other_boat.heading_degrees = 315.0
    ai_boat.speed_knots = 10.0
    other_boat.speed_knots = 10.0
    scenario.race_state.elapsed_seconds = 20.0

    assert not should_tack_to_avoid_collision(ai_boat, scenario)


def test_same_tack_windward_ai_tacks_before_projected_upwind_collision():
    scenario = default_scenario()
    windward_ai = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.AI)
    leeward_boat = scenario.boats[0]
    windward_ai.has_started = True
    leeward_boat.has_started = True
    windward_ai.position = Vector2(400.0, 400.0)
    leeward_boat.position = Vector2(375.0, 405.0)
    windward_ai.heading_degrees = 285.0
    leeward_boat.heading_degrees = 290.0
    windward_ai.speed_knots = 10.0
    leeward_boat.speed_knots = 10.0
    scenario.race_state.elapsed_seconds = 20.0

    update_ai_heading(windward_ai, scenario)

    assert windward_ai.heading_degrees == 15.0
    assert windward_ai.speed_knots == 6.5


def test_ai_keeps_rounding_waypoint_priority_in_windward_mark_traffic():
    scenario = default_scenario()
    windward_mark = next(mark for mark in scenario.course.marks if mark.mark_type == MarkType.WINDWARD)
    windward_ai, leeward_ai = [boat for boat in scenario.boats if boat.control_mode == BoatControlMode.AI]
    windward_ai.has_started = True
    leeward_ai.has_started = True
    windward_ai.target_leg_index = 0
    leeward_ai.target_leg_index = 0
    windward_ai.position = Vector2(windward_mark.position.x - 20.0, windward_mark.position.y + 90.0)
    leeward_ai.position = Vector2(windward_mark.position.x - 45.0, windward_mark.position.y + 95.0)
    windward_ai.heading_degrees = 285.0
    leeward_ai.heading_degrees = 290.0
    windward_ai.speed_knots = 10.0
    leeward_ai.speed_knots = 10.0
    scenario.race_state.elapsed_seconds = 20.0

    assert collision_avoidance_maneuver(windward_ai, scenario) is None


def test_same_tack_leeward_ai_holds_right_of_way_before_projected_collision():
    scenario = default_scenario()
    leeward_ai = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.AI)
    windward_boat = scenario.boats[0]
    leeward_ai.has_started = True
    windward_boat.has_started = True
    leeward_ai.position = Vector2(375.0, 405.0)
    windward_boat.position = Vector2(400.0, 400.0)
    leeward_ai.heading_degrees = 290.0
    windward_boat.heading_degrees = 285.0
    leeward_ai.speed_knots = 10.0
    windward_boat.speed_knots = 10.0
    scenario.race_state.elapsed_seconds = 20.0

    assert collision_avoidance_maneuver(leeward_ai, scenario) is None


def test_same_tack_windward_ai_gybes_before_projected_downwind_collision():
    scenario = default_scenario()
    windward_ai = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.AI)
    leeward_boat = scenario.boats[0]
    windward_ai.has_started = True
    leeward_boat.has_started = True
    windward_ai.target_leg_index = 1
    leeward_boat.target_leg_index = 1
    windward_ai.position = Vector2(400.0, 400.0)
    leeward_boat.position = Vector2(425.0, 405.0)
    windward_ai.heading_degrees = 100.0
    leeward_boat.heading_degrees = 105.0
    windward_ai.speed_knots = 10.0
    leeward_boat.speed_knots = 10.0
    scenario.race_state.elapsed_seconds = 20.0

    update_ai_heading(windward_ai, scenario)

    assert windward_ai.heading_degrees == 190.0
    assert windward_ai.speed_knots == 7.5


def test_same_tack_windward_boat_hitting_leeward_boat_takes_two_turn_penalty():
    scenario = default_scenario()
    windward_boat, leeward_boat = scenario.boats[0], scenario.boats[1]
    windward_boat.has_started = True
    leeward_boat.has_started = True
    windward_boat.heading_degrees = 315.0
    leeward_boat.heading_degrees = 315.0
    windward_boat.position = Vector2(420.0, 420.0)
    leeward_boat.position = Vector2(430.0, 430.0)
    windward_boat.speed_knots = 5.0
    leeward_boat.speed_knots = 5.0

    detect_race_events(scenario, {})

    assert windward_boat.penalty_turn_remaining_degrees == 720.0
    assert windward_boat.penalties_taken == 1
    assert windward_boat.speed_knots == 0.0
    assert leeward_boat.speed_knots == 5.0
    assert any(event.event_type == RaceEventType.RULE_PENALTY for event in scenario.race_state.events)
    assert not any(event.event_type == RaceEventType.BOAT_COLLISION for event in scenario.race_state.events)


def test_ai_collision_escape_holds_separate_directions_for_random_periods():
    scenario = default_scenario()
    first, second = [boat for boat in scenario.boats if boat.control_mode == BoatControlMode.AI]
    first.position = Vector2(400.0, 400.0)
    second.position = Vector2(410.0, 400.0)
    first.heading_degrees = 315.0
    second.heading_degrees = 315.0

    detect_race_events(scenario, {})

    assert first.ai_collision_escape_heading is not None
    assert second.ai_collision_escape_heading is not None
    assert first.ai_collision_escape_heading != second.ai_collision_escape_heading
    assert AI_COLLISION_ESCAPE_MIN_SECONDS <= first.ai_collision_escape_until_seconds <= AI_COLLISION_ESCAPE_MAX_SECONDS
    assert AI_COLLISION_ESCAPE_MIN_SECONDS <= second.ai_collision_escape_until_seconds <= AI_COLLISION_ESCAPE_MAX_SECONDS
    assert first.ai_collision_escape_until_seconds != second.ai_collision_escape_until_seconds

    step_scenario(scenario, 1.0)

    assert scenario.race_state.elapsed_seconds < first.ai_collision_escape_until_seconds
    assert first.ai_collision_escape_heading is not None
    assert second.ai_collision_escape_heading is not None


def test_boat_is_clamped_and_stopped_at_course_boundary():
    scenario = default_scenario()
    boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.USER)
    boat.position = Vector2(scenario.course.boundary_width - 1.0, 450.0)
    boat.heading_degrees = 90.0
    boat.speed_knots = 20.0

    step_scenario(scenario, 10.0)

    assert boat.position.x == scenario.course.boundary_width
    assert boat.speed_knots == 0.0


def test_mark_collision_creates_event():
    scenario = default_scenario()
    scenario.boats[0].position = scenario.course.marks[0].position

    detect_race_events(scenario, {})

    assert any(event.event_type == RaceEventType.MARK_COLLISION for event in scenario.race_state.events)
