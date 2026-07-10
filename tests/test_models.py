from sailing_simulator.domain.models import MarkType, RaceFormat, default_scenario
from sailing_simulator.domain.presets import adapt_course_to_format, course_for_format, remove_invalid_marks
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


def test_adapting_w_course_to_t3_adds_gybe_and_uses_leeward_as_finish():
    course = course_for_format(RaceFormat.W2)

    adapt_course_to_format(course, RaceFormat.T3)

    assert course.race_format == RaceFormat.T3
    assert {mark.mark_type for mark in course.marks} == {
        MarkType.WINDWARD,
        MarkType.GYBE,
        MarkType.FINISH,
    }


def test_adapting_t3_back_to_w_course_uses_finish_as_leeward():
    course = course_for_format(RaceFormat.T3)

    adapt_course_to_format(course, RaceFormat.W4)

    assert course.race_format == RaceFormat.W4
    assert {mark.mark_type for mark in course.marks} == {
        MarkType.WINDWARD,
        MarkType.LEEWARD,
    }


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
