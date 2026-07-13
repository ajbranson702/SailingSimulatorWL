from __future__ import annotations

from sailing_simulator.domain.models import Boat, Course, Mark, MarkType, RaceFormat, Vector2


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


def ranking_key(course: Course, boat: Boat) -> tuple[int, float, float, str]:
    if boat.is_finished and boat.finish_time_seconds is not None:
        return (0, boat.finish_time_seconds, 0.0, boat.name)

    target = target_mark_for(course, boat.target_leg_index)
    if target is None:
        target_position = finish_position_for(course)
    else:
        target_position = target.position

    return (
        1,
        -boat.target_leg_index,
        distance(boat.position, target_position),
        boat.name,
    )


def ranked_boats(course: Course, boats: list[Boat]) -> list[Boat]:
    return sorted(boats, key=lambda boat: ranking_key(course, boat))


def finish_position_for(course: Course) -> Vector2:
    explicit_finish = next((mark.position for mark in course.marks if mark.mark_type == MarkType.FINISH), None)
    if explicit_finish is not None:
        return explicit_finish

    leeward = next((mark.position for mark in course.marks if mark.mark_type == MarkType.LEEWARD), None)
    if leeward is not None:
        return leeward

    start = course.start_line
    return Vector2(
        (start.pin.x + start.committee_boat.x) * 0.5,
        (start.pin.y + start.committee_boat.y) * 0.5,
    )


def distance(first: Vector2, second: Vector2) -> float:
    return ((first.x - second.x) ** 2 + (first.y - second.y) ** 2) ** 0.5
