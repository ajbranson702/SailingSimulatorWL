from sailing_simulator.domain.models import MarkType, RaceFormat, TerrainObject, TerrainType, Vector2, default_scenario
from sailing_simulator.domain.presets import adapt_course_to_format, course_for_format, remove_invalid_marks
from sailing_simulator.domain.serialization import load_scenario, save_scenario, scenario_from_dict, scenario_to_dict
from sailing_simulator.domain.validation import validate_course


def test_default_scenario_has_phase_one_course_and_boats():
    scenario = default_scenario()

    assert scenario.course.race_format == RaceFormat.W2
    assert len(scenario.course.marks) == 2
    assert len(scenario.boats) == 3
    assert scenario.race_state.time_scale == 10.0


def test_supported_race_formats_include_triangle_and_long_course():
    assert {race_format.value for race_format in RaceFormat} == {"W2", "T3", "W4", "W6"}


def test_course_presets_include_required_marks():
    assert {mark.mark_type for mark in course_for_format(RaceFormat.W2).marks} == {
        MarkType.WINDWARD,
        MarkType.LEEWARD,
    }
    assert {mark.mark_type for mark in course_for_format(RaceFormat.T3).marks} == {
        MarkType.WINDWARD,
        MarkType.GYBE,
        MarkType.LEEWARD,
    }


def test_course_validation_accepts_presets():
    for race_format in RaceFormat:
        assert validate_course(course_for_format(race_format)) == []


def test_scenario_serialization_round_trip_preserves_course():
    scenario = default_scenario()
    scenario.course = course_for_format(RaceFormat.T3)
    scenario.wind_model.base_speed_knots = 14.0
    scenario.race_state.time_scale = 25.0
    scenario.race_state.start_sequence_seconds = 180.0
    scenario.boats[0].is_early_start = True
    scenario.boats[1].ai_start_strategy = "committee"

    restored = scenario_from_dict(scenario_to_dict(scenario))

    assert restored.course.race_format == RaceFormat.T3
    assert restored.wind_model.base_speed_knots == 14.0
    assert restored.race_state.time_scale == 25.0
    assert restored.race_state.start_sequence_seconds == 180.0
    assert restored.boats[0].is_early_start
    assert restored.boats[1].ai_start_strategy == "committee"
    assert [mark.mark_type for mark in restored.course.marks] == [
        MarkType.WINDWARD,
        MarkType.GYBE,
        MarkType.LEEWARD,
    ]


def test_scenario_serialization_round_trip_preserves_terrain():
    scenario = default_scenario()
    scenario.terrain.append(TerrainObject(TerrainType.TREES, Vector2(250.0, 300.0), 35.0, 140.0))

    restored = scenario_from_dict(scenario_to_dict(scenario))

    assert len(restored.terrain) == 1
    assert restored.terrain[0].terrain_type == TerrainType.TREES
    assert restored.terrain[0].position == Vector2(250.0, 300.0)
    assert restored.terrain[0].height == 35.0
    assert restored.terrain[0].influence_radius == 140.0


def test_saved_configuration_file_preserves_multiple_terrain_objects(tmp_path):
    scenario = default_scenario()
    scenario.terrain.append(TerrainObject(TerrainType.TREES, Vector2(250.0, 300.0), 35.0, 140.0))
    scenario.terrain.append(TerrainObject(TerrainType.CLIFF, Vector2(700.0, 160.0), 80.0, 260.0))
    path = tmp_path / "terrain_config.json"

    save_scenario(scenario, path)
    restored = load_scenario(path)

    assert [(terrain.terrain_type, terrain.position, terrain.height, terrain.influence_radius) for terrain in restored.terrain] == [
        (TerrainType.TREES, Vector2(250.0, 300.0), 35.0, 140.0),
        (TerrainType.CLIFF, Vector2(700.0, 160.0), 80.0, 260.0),
    ]


def test_adapting_w_course_to_t3_adds_gybe_and_keeps_leeward_mark():
    course = course_for_format(RaceFormat.W2)

    adapt_course_to_format(course, RaceFormat.T3)

    assert course.race_format == RaceFormat.T3
    assert {mark.mark_type for mark in course.marks} == {
        MarkType.WINDWARD,
        MarkType.GYBE,
        MarkType.LEEWARD,
    }


def test_adapting_t3_back_to_w_course_removes_gybe_mark():
    course = course_for_format(RaceFormat.T3)

    adapt_course_to_format(course, RaceFormat.W4)

    assert course.race_format == RaceFormat.W4
    assert {mark.mark_type for mark in course.marks} == {
        MarkType.WINDWARD,
        MarkType.LEEWARD,
    }


def test_loading_legacy_t3_finish_mark_converts_it_to_leeward():
    scenario = default_scenario()
    scenario.course = course_for_format(RaceFormat.T3)
    leeward = next(mark for mark in scenario.course.marks if mark.mark_type == MarkType.LEEWARD)
    leeward.mark_type = MarkType.FINISH
    leeward.label = "F"

    restored = scenario_from_dict(scenario_to_dict(scenario))

    assert {mark.mark_type for mark in restored.course.marks} == {
        MarkType.WINDWARD,
        MarkType.GYBE,
        MarkType.LEEWARD,
    }
    assert next(mark for mark in restored.course.marks if mark.mark_type == MarkType.LEEWARD).label == "L"


def test_adapting_t3_to_w2_removes_gybe_mark():
    course = course_for_format(RaceFormat.T3)

    adapt_course_to_format(course, RaceFormat.W2)

    assert MarkType.GYBE not in {mark.mark_type for mark in course.marks}


def test_remove_invalid_marks_deletes_marks_not_allowed_for_format():
    course = course_for_format(RaceFormat.W2)
    course.marks.append(course_for_format(RaceFormat.T3).marks[1])

    removed = remove_invalid_marks(course)

    assert [mark.mark_type for mark in removed] == [MarkType.GYBE]
    assert MarkType.GYBE not in {mark.mark_type for mark in course.marks}
