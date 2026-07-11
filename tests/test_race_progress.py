from sailing_simulator.domain.models import MarkType, RaceFormat
from sailing_simulator.domain.race_progress import mark_sequence_for


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
