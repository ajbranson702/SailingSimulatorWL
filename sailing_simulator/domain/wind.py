from __future__ import annotations

import math

from sailing_simulator.domain.models import Scenario, Vector2, WindCell, WindMode, WindModel


def update_wind_field(scenario: Scenario) -> None:
    field = scenario.wind_field
    field.cells = []
    x_step = scenario.course.boundary_width / max(field.columns, 1)
    y_step = scenario.course.boundary_height / max(field.rows, 1)

    for row in range(field.rows):
        for column in range(field.columns):
            center = Vector2(column * x_step + x_step * 0.5, row * y_step + y_step * 0.5)
            direction, speed = wind_at(scenario, center)
            field.cells.append(WindCell(column, row, center, direction, speed))


def wind_at(scenario: Scenario, position: Vector2) -> tuple[float, float]:
    model = scenario.wind_model
    elapsed = scenario.race_state.elapsed_seconds
    return direction_at(model, elapsed), speed_at(model, elapsed, position)


def direction_at(model: WindModel, elapsed_seconds: float) -> float:
    direction = model.base_direction_degrees
    if model.mode == WindMode.OSCILLATING:
        direction += oscillation(model, elapsed_seconds)
    elif model.mode == WindMode.PERSISTENT_LEFT:
        direction -= persistent_shift(model, elapsed_seconds)
    elif model.mode == WindMode.PERSISTENT_RIGHT:
        direction += persistent_shift(model, elapsed_seconds)
    elif model.mode == WindMode.PERSISTENT_WITH_OSCILLATION:
        direction += persistent_shift(model, elapsed_seconds)
        direction += oscillation(model, elapsed_seconds)

    return normalize_degrees(direction)


def speed_at(model: WindModel, elapsed_seconds: float, position: Vector2) -> float:
    gust_factor = model.gust_percent / 100.0
    if gust_factor <= 0.0:
        return model.base_speed_knots

    wave = math.sin(elapsed_seconds / 18.0 + position.x / 170.0 + position.y / 230.0)
    return max(0.0, model.base_speed_knots * (1.0 + gust_factor * wave))


def oscillation(model: WindModel, elapsed_seconds: float) -> float:
    period = max(model.oscillation_period_seconds, 1.0)
    return model.oscillation_amplitude_degrees * math.sin((elapsed_seconds / period) * math.tau)


def persistent_shift(model: WindModel, elapsed_seconds: float) -> float:
    return model.persistent_shift_degrees_per_minute * (elapsed_seconds / 60.0)


def normalize_degrees(degrees: float) -> float:
    return degrees % 360.0
