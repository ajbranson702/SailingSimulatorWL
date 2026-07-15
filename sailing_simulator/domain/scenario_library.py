from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sailing_simulator.domain.models import RaceFormat, Scenario, TerrainObject, TerrainType, Vector2, WindMode, default_scenario
from sailing_simulator.domain.presets import course_for_format
from sailing_simulator.domain.simulation import reset_boats_to_start
from sailing_simulator.domain.wind import update_wind_field


@dataclass(frozen=True)
class ScenarioTemplate:
    name: str
    description: str
    builder: Callable[[], Scenario]


def built_in_scenarios() -> list[ScenarioTemplate]:
    return [
        ScenarioTemplate("W2 Training", "Standard windward-leeward race with steady breeze.", _w2_training),
        ScenarioTemplate("T3 Gybe Mark", "Triangle-style course with a gybe mark and steady wind.", _t3_gybe_mark),
        ScenarioTemplate("Gusty Terrain W4", "Two-lap windward-leeward course with oscillations, gusts, and terrain.", _gusty_terrain_w4),
    ]


def scenario_template_by_name(name: str) -> ScenarioTemplate:
    for template in built_in_scenarios():
        if template.name == name:
            return template
    raise KeyError(name)


def _base_scenario(race_format: RaceFormat) -> Scenario:
    scenario = default_scenario()
    scenario.course = course_for_format(race_format)
    reset_boats_to_start(scenario)
    scenario.race_state.is_running = False
    scenario.race_state.elapsed_seconds = 0.0
    return scenario


def _w2_training() -> Scenario:
    scenario = _base_scenario(RaceFormat.W2)
    scenario.wind_model.mode = WindMode.STATIC
    scenario.wind_model.base_speed_knots = 10.0
    scenario.wind_model.base_direction_degrees = 0.0
    update_wind_field(scenario)
    return scenario


def _t3_gybe_mark() -> Scenario:
    scenario = _base_scenario(RaceFormat.T3)
    scenario.wind_model.mode = WindMode.OSCILLATING
    scenario.wind_model.base_speed_knots = 10.0
    scenario.wind_model.base_direction_degrees = 5.0
    scenario.wind_model.oscillation_amplitude_degrees = 8.0
    scenario.wind_model.oscillation_period_seconds = 180.0
    update_wind_field(scenario)
    return scenario


def _gusty_terrain_w4() -> Scenario:
    scenario = _base_scenario(RaceFormat.W4)
    scenario.wind_model.mode = WindMode.PERSISTENT_WITH_OSCILLATION
    scenario.wind_model.base_speed_knots = 12.0
    scenario.wind_model.base_direction_degrees = -8.0
    scenario.wind_model.oscillation_amplitude_degrees = 12.0
    scenario.wind_model.oscillation_period_seconds = 210.0
    scenario.wind_model.persistent_shift_degrees_per_minute = 2.0
    scenario.wind_model.gust_percent = 12.0
    scenario.terrain = [
        TerrainObject(TerrainType.HILL, Vector2(160.0, 160.0), 45.0, 160.0),
        TerrainObject(TerrainType.TREES, Vector2(760.0, 310.0), 28.0, 140.0),
    ]
    update_wind_field(scenario)
    return scenario
