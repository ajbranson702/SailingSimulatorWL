from __future__ import annotations

from sailing_simulator.domain.models import Course, Mark, MarkType, RaceFormat


def mark_sequence_for(race_format: RaceFormat) -> list[MarkType]:
    if race_format == RaceFormat.W2:
        return [MarkType.WINDWARD]
    if race_format == RaceFormat.T3:
        return [MarkType.WINDWARD, MarkType.GYBE]
    if race_format == RaceFormat.W4:
        return [MarkType.WINDWARD, MarkType.LEEWARD, MarkType.WINDWARD]
    if race_format == RaceFormat.W6:
        return [
            MarkType.WINDWARD,
            MarkType.LEEWARD,
            MarkType.WINDWARD,
            MarkType.LEEWARD,
            MarkType.WINDWARD,
        ]
    raise ValueError(f"Unsupported race format: {race_format}")


def target_mark_for(course: Course, target_leg_index: int) -> Mark | None:
    sequence = mark_sequence_for(course.race_format)
    if target_leg_index >= len(sequence):
        return None

    mark_type = sequence[target_leg_index]
    return next((mark for mark in course.marks if mark.mark_type == mark_type), None)


def target_label_for(course: Course, target_leg_index: int) -> str:
    target = target_mark_for(course, target_leg_index)
    if target is None:
        return "Finish"
    return target.label


def total_targets_for(course: Course) -> int:
    return len(mark_sequence_for(course.race_format))
