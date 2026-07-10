from __future__ import annotations

from sailing_simulator.domain.models import Course, Mark, MarkType, RaceFormat, StartLine, Vector2


def course_for_format(race_format: RaceFormat) -> Course:
    marks = {
        RaceFormat.W2: [
            Mark(MarkType.WINDWARD, Vector2(460.0, 160.0), "W"),
            Mark(MarkType.LEEWARD, Vector2(460.0, 720.0), "L/F"),
        ],
        RaceFormat.T3: [
            Mark(MarkType.WINDWARD, Vector2(460.0, 160.0), "W"),
            Mark(MarkType.GYBE, Vector2(650.0, 420.0), "G"),
            Mark(MarkType.FINISH, Vector2(460.0, 720.0), "F"),
        ],
        RaceFormat.W4: [
            Mark(MarkType.WINDWARD, Vector2(460.0, 160.0), "W"),
            Mark(MarkType.LEEWARD, Vector2(460.0, 720.0), "L/F"),
        ],
        RaceFormat.W6: [
            Mark(MarkType.WINDWARD, Vector2(460.0, 160.0), "W"),
            Mark(MarkType.LEEWARD, Vector2(460.0, 720.0), "L/F"),
        ],
    }
    return Course(
        race_format=race_format,
        start_line=StartLine(),
        marks=[Mark(mark.mark_type, mark.position, mark.label) for mark in marks[race_format]],
    )


def required_mark_types_for(race_format: RaceFormat) -> set[MarkType]:
    if race_format == RaceFormat.T3:
        return {MarkType.WINDWARD, MarkType.GYBE, MarkType.FINISH}
    return {MarkType.WINDWARD, MarkType.LEEWARD}
