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


def valid_mark_types_for(race_format: RaceFormat) -> set[MarkType]:
    return required_mark_types_for(race_format)


def adapt_course_to_format(course: Course, race_format: RaceFormat) -> None:
    course.race_format = race_format
    if race_format == RaceFormat.T3:
        _convert_mark(course, MarkType.LEEWARD, MarkType.FINISH, "F")
        _ensure_mark(course, MarkType.WINDWARD, Vector2(460.0, 160.0), "W")
        _ensure_mark(course, MarkType.GYBE, Vector2(650.0, 420.0), "G")
        _ensure_mark(course, MarkType.FINISH, Vector2(460.0, 720.0), "F")
        remove_invalid_marks(course)
        return

    _convert_mark(course, MarkType.FINISH, MarkType.LEEWARD, "L/F")
    _ensure_mark(course, MarkType.WINDWARD, Vector2(460.0, 160.0), "W")
    _ensure_mark(course, MarkType.LEEWARD, Vector2(460.0, 720.0), "L/F")
    remove_invalid_marks(course)


def add_gybe_mark(course: Course) -> Mark:
    return _ensure_mark(course, MarkType.GYBE, Vector2(650.0, 420.0), "G")


def invalid_marks_for(course: Course) -> list[Mark]:
    valid_types = valid_mark_types_for(course.race_format)
    return [mark for mark in course.marks if mark.mark_type not in valid_types]


def remove_invalid_marks(course: Course) -> list[Mark]:
    invalid_marks = invalid_marks_for(course)
    if not invalid_marks:
        return []

    invalid_ids = {id(mark) for mark in invalid_marks}
    course.marks = [mark for mark in course.marks if id(mark) not in invalid_ids]
    return invalid_marks


def _ensure_mark(course: Course, mark_type: MarkType, position: Vector2, label: str) -> Mark:
    existing = _find_mark(course, mark_type)
    if existing is not None:
        if not existing.label:
            existing.label = label
        return existing

    mark = Mark(mark_type, position, label)
    course.marks.append(mark)
    return mark


def _convert_mark(course: Course, old_type: MarkType, new_type: MarkType, label: str) -> None:
    if _find_mark(course, new_type) is not None:
        return

    mark = _find_mark(course, old_type)
    if mark is None:
        return

    mark.mark_type = new_type
    mark.label = label


def _find_mark(course: Course, mark_type: MarkType) -> Mark | None:
    return next((mark for mark in course.marks if mark.mark_type == mark_type), None)
