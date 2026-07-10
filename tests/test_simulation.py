from sailing_simulator.domain.models import BoatControlMode, RaceEventType, Vector2, default_scenario
from sailing_simulator.domain.simulation import (
    detect_race_events,
    step_scenario,
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


def test_finish_crossing_creates_event_once():
    scenario = default_scenario()
    boat = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.USER)
    previous = Vector2(450.0, 710.0)
    boat.position = Vector2(450.0, 690.0)

    detect_race_events(scenario, {boat.name: previous})
    detect_race_events(scenario, {boat.name: previous})

    assert boat.name in scenario.race_state.finished_boats
    assert [event.event_type for event in scenario.race_state.events].count(RaceEventType.FINISH_CROSSED) == 1


def test_boat_collision_creates_event():
    scenario = default_scenario()
    scenario.boats[0].position = Vector2(400.0, 400.0)
    scenario.boats[1].position = Vector2(410.0, 400.0)

    detect_race_events(scenario, {})

    assert any(event.event_type == RaceEventType.BOAT_COLLISION for event in scenario.race_state.events)


def test_mark_collision_creates_event():
    scenario = default_scenario()
    scenario.boats[0].position = scenario.course.marks[0].position

    detect_race_events(scenario, {})

    assert any(event.event_type == RaceEventType.MARK_COLLISION for event in scenario.race_state.events)
