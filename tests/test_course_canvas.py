import pytest
from PySide6.QtWidgets import QApplication

from sailing_simulator.domain.models import default_scenario
from sailing_simulator.ui.course_canvas import CourseCanvas, DragTarget


def test_sail_side_moves_opposite_relative_wind():
    app = QApplication.instance() or QApplication([])
    canvas = CourseCanvas(default_scenario())

    canvas.scenario.wind_model.base_direction_degrees = 0.0

    assert canvas._sail_side_for(45.0) == 1
    assert canvas._sail_side_for(315.0) == -1

    app.quit()


def test_boats_can_only_be_dragged_before_race_start():
    app = QApplication.instance() or QApplication([])
    scenario = default_scenario()
    canvas = CourseCanvas(scenario)
    canvas.resize(900, 900)

    boat = scenario.boats[0]
    boat_screen_position = canvas._to_screen(boat.position, canvas._course_rect())
    boat.speed_knots = 5.0
    boat.track = [boat.position]

    assert canvas._hit_test(boat_screen_position).kind == "boat"

    canvas._drag_target = DragTarget("boat", 0)
    canvas._move_drag_target(canvas._to_screen(scenario.course.marks[0].position, canvas._course_rect()))

    assert boat.position.x == pytest.approx(scenario.course.marks[0].position.x)
    assert boat.position.y == pytest.approx(scenario.course.marks[0].position.y)
    assert boat.speed_knots == 0.0
    assert boat.track == []

    scenario.race_state.elapsed_seconds = 1.0

    target = canvas._hit_test(canvas._to_screen(boat.position, canvas._course_rect()))
    assert target is None or target.kind != "boat"

    app.quit()
