from sailing_simulator.domain.models import Vector2, WindMode, default_scenario
from sailing_simulator.domain.wind import direction_at, update_wind_field, wind_at


def test_static_wind_uses_base_direction_and_speed():
    scenario = default_scenario()
    scenario.wind_model.base_direction_degrees = 12.0
    scenario.wind_model.base_speed_knots = 9.0

    direction, speed = wind_at(scenario, Vector2(100.0, 100.0))

    assert direction == 12.0
    assert speed == 9.0


def test_oscillating_wind_changes_direction_over_time():
    scenario = default_scenario()
    scenario.wind_model.mode = WindMode.OSCILLATING
    scenario.wind_model.oscillation_amplitude_degrees = 20.0
    scenario.wind_model.oscillation_period_seconds = 120.0

    assert round(direction_at(scenario.wind_model, 30.0), 1) == 20.0


def test_persistent_left_wind_shifts_left_over_time():
    scenario = default_scenario()
    scenario.wind_model.mode = WindMode.PERSISTENT_LEFT
    scenario.wind_model.persistent_shift_degrees_per_minute = 5.0

    assert direction_at(scenario.wind_model, 120.0) == 350.0


def test_persistent_left_with_oscillation_shifts_left_and_oscillates():
    scenario = default_scenario()
    scenario.wind_model.mode = WindMode.PERSISTENT_LEFT_WITH_OSCILLATION
    scenario.wind_model.persistent_shift_degrees_per_minute = 5.0
    scenario.wind_model.oscillation_amplitude_degrees = 20.0
    scenario.wind_model.oscillation_period_seconds = 120.0

    assert direction_at(scenario.wind_model, 30.0) == 17.5


def test_gusts_vary_wind_speed_by_position():
    scenario = default_scenario()
    scenario.wind_model.gust_percent = 20.0

    _, first_speed = wind_at(scenario, Vector2(100.0, 100.0))
    _, second_speed = wind_at(scenario, Vector2(500.0, 500.0))

    assert first_speed != second_speed


def test_update_wind_field_populates_cells():
    scenario = default_scenario()

    update_wind_field(scenario)

    assert len(scenario.wind_field.cells) == scenario.wind_field.columns * scenario.wind_field.rows
