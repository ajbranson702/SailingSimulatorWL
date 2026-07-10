from __future__ import annotations

from sailing_simulator.domain.models import Course
from sailing_simulator.domain.presets import required_mark_types_for


def validate_course(course: Course) -> list[str]:
    errors: list[str] = []
    start = course.start_line

    if start.pin == start.committee_boat:
        errors.append("Start line endpoints must not be in the same position.")

    present_mark_types = {mark.mark_type for mark in course.marks}
    for mark_type in sorted(required_mark_types_for(course.race_format), key=lambda item: item.value):
        if mark_type not in present_mark_types:
            errors.append(f"Course format {course.race_format.value} requires a {mark_type.value} mark.")

    return errors
