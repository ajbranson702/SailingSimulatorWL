from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sailing_simulator.domain.models import (
    Boat,
    BoatControlMode,
    Course,
    Mark,
    MarkType,
    Polar,
    RaceEvent,
    RaceEventType,
    RaceFormat,
    RaceState,
    Scenario,
    StartLine,
    TerrainObject,
    TerrainType,
    Vector2,
    WindField,
    WindMode,
    WindModel,
)


SCENARIO_VERSION = 1


def save_scenario(scenario: Scenario, path: str | Path) -> None:
    Path(path).write_text(json.dumps(scenario_to_dict(scenario), indent=2), encoding="utf-8")


def load_scenario(path: str | Path) -> Scenario:
    return scenario_from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def scenario_to_dict(scenario: Scenario) -> dict[str, Any]:
    return {
        "version": SCENARIO_VERSION,
        "course": course_to_dict(scenario.course),
        "boats": [boat_to_dict(boat) for boat in scenario.boats],
        "wind_model": wind_model_to_dict(scenario.wind_model),
        "wind_field": {
            "columns": scenario.wind_field.columns,
            "rows": scenario.wind_field.rows,
            "cell_size": scenario.wind_field.cell_size,
        },
        "polar": {
            "name": scenario.polar.name,
            "speeds_by_tws_and_twa": scenario.polar.speeds_by_tws_and_twa,
        },
        "terrain": [terrain_to_dict(terrain) for terrain in scenario.terrain],
        "race_state": {
            "elapsed_seconds": scenario.race_state.elapsed_seconds,
            "is_running": scenario.race_state.is_running,
            "time_scale": scenario.race_state.time_scale,
            "events": [race_event_to_dict(event) for event in scenario.race_state.events],
            "finished_boats": sorted(scenario.race_state.finished_boats),
        },
    }


def scenario_from_dict(data: dict[str, Any]) -> Scenario:
    return Scenario(
        course=course_from_dict(data["course"]),
        boats=[boat_from_dict(boat) for boat in data.get("boats", [])],
        wind_model=wind_model_from_dict(data.get("wind_model", {})),
        wind_field=WindField(**data.get("wind_field", {})),
        polar=polar_from_dict(data.get("polar", {})),
        terrain=[terrain_from_dict(terrain) for terrain in data.get("terrain", [])],
        race_state=race_state_from_dict(data.get("race_state", {})),
    )


def race_state_from_dict(data: dict[str, Any]) -> RaceState:
    return RaceState(
        elapsed_seconds=float(data.get("elapsed_seconds", 0.0)),
        is_running=bool(data.get("is_running", False)),
        time_scale=float(data.get("time_scale", 10.0)),
        events=[race_event_from_dict(event) for event in data.get("events", [])],
        finished_boats=set(data.get("finished_boats", [])),
    )


def race_event_to_dict(event: RaceEvent) -> dict[str, Any]:
    return {
        "event_type": event.event_type.value,
        "message": event.message,
        "elapsed_seconds": event.elapsed_seconds,
    }


def race_event_from_dict(data: dict[str, Any]) -> RaceEvent:
    return RaceEvent(
        event_type=RaceEventType(data["event_type"]),
        message=data["message"],
        elapsed_seconds=float(data.get("elapsed_seconds", 0.0)),
    )


def course_to_dict(course: Course) -> dict[str, Any]:
    return {
        "race_format": course.race_format.value,
        "start_line": {
            "pin": vector_to_dict(course.start_line.pin),
            "committee_boat": vector_to_dict(course.start_line.committee_boat),
        },
        "marks": [mark_to_dict(mark) for mark in course.marks],
        "boundary_width": course.boundary_width,
        "boundary_height": course.boundary_height,
    }


def course_from_dict(data: dict[str, Any]) -> Course:
    start_line = data.get("start_line", {})
    return Course(
        race_format=RaceFormat(data.get("race_format", RaceFormat.W2.value)),
        start_line=StartLine(
            pin=vector_from_dict(start_line.get("pin", {}), Vector2(360.0, 700.0)),
            committee_boat=vector_from_dict(start_line.get("committee_boat", {}), Vector2(560.0, 700.0)),
        ),
        marks=[mark_from_dict(mark) for mark in data.get("marks", [])],
        boundary_width=float(data.get("boundary_width", 900.0)),
        boundary_height=float(data.get("boundary_height", 900.0)),
    )


def mark_to_dict(mark: Mark) -> dict[str, Any]:
    return {"mark_type": mark.mark_type.value, "position": vector_to_dict(mark.position), "label": mark.label}


def mark_from_dict(data: dict[str, Any]) -> Mark:
    return Mark(
        mark_type=MarkType(data["mark_type"]),
        position=vector_from_dict(data["position"], Vector2(0.0, 0.0)),
        label=data.get("label", data["mark_type"].upper()),
    )


def boat_to_dict(boat: Boat) -> dict[str, Any]:
    return {
        "name": boat.name,
        "position": vector_to_dict(boat.position),
        "heading_degrees": boat.heading_degrees,
        "speed_knots": boat.speed_knots,
        "control_mode": boat.control_mode.value,
        "target_leg_index": boat.target_leg_index,
        "track": [vector_to_dict(point) for point in boat.track],
    }


def boat_from_dict(data: dict[str, Any]) -> Boat:
    return Boat(
        name=data["name"],
        position=vector_from_dict(data["position"], Vector2(0.0, 0.0)),
        heading_degrees=float(data.get("heading_degrees", 0.0)),
        speed_knots=float(data.get("speed_knots", 0.0)),
        control_mode=BoatControlMode(data.get("control_mode", BoatControlMode.AI.value)),
        target_leg_index=int(data.get("target_leg_index", 0)),
        track=[vector_from_dict(point, Vector2(0.0, 0.0)) for point in data.get("track", [])],
    )


def wind_model_to_dict(wind_model: WindModel) -> dict[str, Any]:
    return {
        "mode": wind_model.mode.value,
        "base_direction_degrees": wind_model.base_direction_degrees,
        "base_speed_knots": wind_model.base_speed_knots,
        "oscillation_amplitude_degrees": wind_model.oscillation_amplitude_degrees,
        "oscillation_period_seconds": wind_model.oscillation_period_seconds,
        "persistent_shift_degrees_per_minute": wind_model.persistent_shift_degrees_per_minute,
        "gust_percent": wind_model.gust_percent,
    }


def wind_model_from_dict(data: dict[str, Any]) -> WindModel:
    return WindModel(
        mode=WindMode(data.get("mode", WindMode.STATIC.value)),
        base_direction_degrees=float(data.get("base_direction_degrees", 0.0)),
        base_speed_knots=float(data.get("base_speed_knots", 10.0)),
        oscillation_amplitude_degrees=float(data.get("oscillation_amplitude_degrees", 10.0)),
        oscillation_period_seconds=float(data.get("oscillation_period_seconds", 180.0)),
        persistent_shift_degrees_per_minute=float(data.get("persistent_shift_degrees_per_minute", 0.0)),
        gust_percent=float(data.get("gust_percent", 0.0)),
    )


def polar_from_dict(data: dict[str, Any]) -> Polar:
    if not data:
        return Polar()
    raw_speeds = data.get("speeds_by_tws_and_twa", {})
    speeds = {
        float(tws): {float(twa): float(speed) for twa, speed in angles.items()}
        for tws, angles in raw_speeds.items()
    }
    return Polar(name=data.get("name", "Default Training Boat"), speeds_by_tws_and_twa=speeds)


def terrain_to_dict(terrain: TerrainObject) -> dict[str, Any]:
    return {
        "terrain_type": terrain.terrain_type.value,
        "position": vector_to_dict(terrain.position),
        "height": terrain.height,
        "influence_radius": terrain.influence_radius,
    }


def terrain_from_dict(data: dict[str, Any]) -> TerrainObject:
    return TerrainObject(
        terrain_type=TerrainType(data["terrain_type"]),
        position=vector_from_dict(data["position"], Vector2(0.0, 0.0)),
        height=float(data["height"]),
        influence_radius=float(data["influence_radius"]),
    )


def vector_to_dict(vector: Vector2) -> dict[str, float]:
    return {"x": vector.x, "y": vector.y}


def vector_from_dict(data: dict[str, Any], fallback: Vector2) -> Vector2:
    return Vector2(float(data.get("x", fallback.x)), float(data.get("y", fallback.y)))
