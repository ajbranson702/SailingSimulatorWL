from sailing_simulator.domain.models import MarkType, RaceFormat, default_scenario
from sailing_simulator.domain.presets import course_for_format
from sailing_simulator.domain.serialization import scenario_from_dict, scenario_to_dict
from sailing_simulator.domain.validation import validate_course


def test_default_scenario_has_phase_one_course_and_boats():
    scenario = default_scenario()

    assert scenario.course.race_format == RaceFormat.W2
    assert len(scenario.course.marks) == 2
    assert len(scenario.boats) == 3


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
        MarkType.FINISH,
    }


def test_course_validation_accepts_presets():
    for race_format in RaceFormat:
        assert validate_course(course_for_format(race_format)) == []


def test_scenario_serialization_round_trip_preserves_course():
    scenario = default_scenario()
    scenario.course = course_for_format(RaceFormat.T3)
    scenario.wind_model.base_speed_knots = 14.0

    restored = scenario_from_dict(scenario_to_dict(scenario))

    assert restored.course.race_format == RaceFormat.T3
    assert restored.wind_model.base_speed_knots == 14.0
    assert [mark.mark_type for mark in restored.course.marks] == [
        MarkType.WINDWARD,
        MarkType.GYBE,
        MarkType.FINISH,
    ]
