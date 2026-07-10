from sailing_simulator.domain.models import BoatControlMode, default_scenario
from sailing_simulator.domain.simulation import (
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
