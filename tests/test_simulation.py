from sailing_simulator.domain.models import BoatControlMode, MarkType, RaceEventType, Vector2, default_scenario
from sailing_simulator.domain.simulation import (
    detect_race_events,
    step_scenario,
    steer_away_from_wind,
    tack,
    target_boat_speed,
    true_wind_angle,
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


def test_mark_rounding_advances_target_leg():
    scenario = default_scenario()
    boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.USER)
    boat.has_started = True
    windward = next(mark for mark in scenario.course.marks if mark.mark_type == MarkType.WINDWARD)
    boat.position = windward.position

    detect_race_events(scenario, {boat.name: boat.position})

    assert boat.target_leg_index == 1
    assert any(event.event_type == RaceEventType.MARK_ROUNDED for event in scenario.race_state.events)


def test_mark_rounding_advances_when_boat_passes_through_mark_radius_between_ticks():
    scenario = default_scenario()
    boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.USER)
    boat.has_started = True
    windward = next(mark for mark in scenario.course.marks if mark.mark_type == MarkType.WINDWARD)
    previous = Vector2(windward.position.x - 80.0, windward.position.y)
    boat.position = Vector2(windward.position.x + 80.0, windward.position.y)

    detect_race_events(scenario, {boat.name: previous})

    assert boat.target_leg_index == 1
    assert any(event.event_type == RaceEventType.MARK_ROUNDED for event in scenario.race_state.events)


def test_finish_crossing_only_counts_after_required_marks():
    scenario = default_scenario()
    boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.USER)
    boat.has_started = True
    boat.target_leg_index = 1
    previous = Vector2(450.0, 690.0)
    boat.position = Vector2(450.0, 710.0)

    detect_race_events(scenario, {boat.name: previous})

    assert boat.is_finished
    assert boat.name in scenario.race_state.finished_boats
    assert any(event.event_type == RaceEventType.FINISH_CROSSED for event in scenario.race_state.events)


def test_finish_counts_when_boat_reaches_finish_mark_after_required_marks():
    scenario = default_scenario()
    boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.USER)
    boat.has_started = True
    boat.target_leg_index = 1
    finish = next(mark for mark in scenario.course.marks if mark.mark_type == MarkType.LEEWARD)
    previous = Vector2(finish.position.x, finish.position.y - 80.0)
    boat.position = Vector2(finish.position.x, finish.position.y + 80.0)

    detect_race_events(scenario, {boat.name: previous})

    assert boat.is_finished
    assert boat.name in scenario.race_state.finished_boats


def test_progress_can_round_last_mark_and_finish_in_one_large_step():
    scenario = default_scenario()
    boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.USER)
    scenario.boats = [boat]
    boat.has_started = True
    windward = next(mark for mark in scenario.course.marks if mark.mark_type == MarkType.WINDWARD)
    previous = Vector2(windward.position.x, windward.position.y - 20.0)
    boat.position = Vector2(windward.position.x, scenario.course.start_line.pin.y + 20.0)

    detect_race_events(scenario, {boat.name: previous})

    assert boat.target_leg_index == 1
    assert boat.is_finished
    assert [event.event_type for event in scenario.race_state.events] == [
        RaceEventType.MARK_ROUNDED,
        RaceEventType.FINISH_CROSSED,
        RaceEventType.MARK_COLLISION,
    ]


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
