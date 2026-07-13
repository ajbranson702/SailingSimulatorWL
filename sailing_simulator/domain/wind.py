from __future__ import annotations

import math

from sailing_simulator.domain.models import Scenario, TerrainObject, TerrainType, Vector2, WindCell, WindMode, WindModel


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
    direction = direction_at(model, elapsed)
    speed = speed_at(model, elapsed, position)
    return apply_terrain_effects(scenario, position, direction, speed)


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
    elif model.mode == WindMode.PERSISTENT_LEFT_WITH_OSCILLATION:
        direction -= persistent_shift(model, elapsed_seconds)
        direction += oscillation(model, elapsed_seconds)
    elif model.mode == WindMode.PERSISTENT_RIGHT_WITH_OSCILLATION:
        direction += persistent_shift(model, elapsed_seconds)
        direction += oscillation(model, elapsed_seconds)

    return normalize_degrees(direction)


def speed_at(model: WindModel, elapsed_seconds: float, position: Vector2) -> float:
    gust_factor = model.gust_percent / 100.0
    if gust_factor <= 0.0:
        return model.base_speed_knots

    wave = math.sin(elapsed_seconds / 18.0 + position.x / 170.0 + position.y / 230.0)
    return max(0.0, model.base_speed_knots * (1.0 + gust_factor * wave))


def apply_terrain_effects(
    scenario: Scenario,
    position: Vector2,
    direction_degrees: float,
    speed_knots: float,
) -> tuple[float, float]:
    direction = direction_degrees
    speed = speed_knots
    for terrain in scenario.terrain:
        direction, speed = apply_single_terrain_effect(terrain, position, direction, speed)
    return normalize_degrees(direction), max(0.0, speed)


def apply_single_terrain_effect(
    terrain: TerrainObject,
    position: Vector2,
    direction_degrees: float,
    speed_knots: float,
) -> tuple[float, float]:
    radius = max(terrain.influence_radius, 1.0)
    dx = position.x - terrain.position.x
    dy = position.y - terrain.position.y
    downwind = wind_downwind_unit(direction_degrees)
    side = Vector2(-downwind.y, downwind.x)
    downwind_distance = dx * downwind.x + dy * downwind.y
    lateral_distance = dx * side.x + dy * side.y

    shadow_length = radius * 3.5
    if downwind_distance < 0.0 or downwind_distance > shadow_length:
        return direction_degrees, speed_knots
    if abs(lateral_distance) > radius * 1.35:
        return direction_degrees, speed_knots

    type_factor = terrain_type_factor(terrain.terrain_type)
    height_factor = max(0.0, min(1.0, terrain.height / 100.0))
    downwind_fade = 1.0 - downwind_distance / shadow_length
    lateral_fade = 1.0 - abs(lateral_distance) / (radius * 1.35)
    influence = max(0.0, downwind_fade * lateral_fade * height_factor * type_factor)

    speed_reduction = min(0.88, influence * 0.82)
    deflection = math.copysign(38.0 * influence, lateral_distance if abs(lateral_distance) > 1e-9 else 1.0)
    turbulence = math.sin((position.x + position.y) / 46.0) * 7.0 * influence
    return normalize_degrees(direction_degrees + deflection + turbulence), speed_knots * (1.0 - speed_reduction)


def wind_downwind_unit(direction_degrees: float) -> Vector2:
    radians = math.radians(direction_degrees + 180.0)
    return Vector2(math.sin(radians), -math.cos(radians))


def terrain_type_factor(terrain_type: TerrainType) -> float:
    factors = {
        TerrainType.HILL: 0.75,
        TerrainType.SHORELINE: 0.45,
        TerrainType.BUILDINGS: 1.0,
        TerrainType.TREES: 0.7,
        TerrainType.CLIFF: 0.9,
    }
    return factors[terrain_type]


def oscillation(model: WindModel, elapsed_seconds: float) -> float:
    period = max(model.oscillation_period_seconds, 1.0)
    return model.oscillation_amplitude_degrees * math.sin((elapsed_seconds / period) * math.tau)


def persistent_shift(model: WindModel, elapsed_seconds: float) -> float:
    return model.persistent_shift_degrees_per_minute * (elapsed_seconds / 60.0)


def normalize_degrees(degrees: float) -> float:
    return degrees % 360.0
