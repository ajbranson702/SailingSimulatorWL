from sailing_simulator.domain.models import RaceFormat, default_scenario


def test_default_scenario_has_phase_one_course_and_boats():
    scenario = default_scenario()

    assert scenario.course.race_format == RaceFormat.W2
    assert len(scenario.course.marks) == 3
    assert len(scenario.boats) == 3


def test_supported_race_formats_include_triangle_and_long_course():
    assert {race_format.value for race_format in RaceFormat} == {"W2", "T3", "W4", "W6"}
