from sailing_simulator.domain.models import BoatControlMode, MarkType, RaceFormat, default_scenario
from sailing_simulator.domain.race_progress import mark_sequence_for, ranked_boats


def test_mark_sequences_match_supported_course_formats():
    assert mark_sequence_for(RaceFormat.W2) == [MarkType.WINDWARD]
    assert mark_sequence_for(RaceFormat.T3) == [MarkType.WINDWARD, MarkType.GYBE]
    assert mark_sequence_for(RaceFormat.W4) == [MarkType.WINDWARD, MarkType.LEEWARD, MarkType.WINDWARD]
    assert mark_sequence_for(RaceFormat.W6) == [
        MarkType.WINDWARD,
        MarkType.LEEWARD,
        MarkType.WINDWARD,
        MarkType.LEEWARD,
        MarkType.WINDWARD,
    ]


def test_rankings_prefer_finished_boats_then_leg_progress():
    scenario = default_scenario()
    user = next(boat for boat in scenario.boats if boat.control_mode == BoatControlMode.USER)
    first_ai = next(boat for boat in scenario.boats if boat.name == "AI 1")
    second_ai = next(boat for boat in scenario.boats if boat.name == "AI 2")
    user.is_finished = True
    user.finish_time_seconds = 120.0
    first_ai.target_leg_index = 1
    second_ai.target_leg_index = 0

    ranked = ranked_boats(scenario.course, scenario.boats)

    assert ranked[:3] == [user, first_ai, second_ai]
