from PySide6.QtWidgets import QApplication

from sailing_simulator.domain.models import default_scenario
from sailing_simulator.ui.course_canvas import CourseCanvas


def test_sail_side_moves_opposite_relative_wind():
    app = QApplication.instance() or QApplication([])
    canvas = CourseCanvas(default_scenario())

    canvas.scenario.wind_model.base_direction_degrees = 0.0

    assert canvas._sail_side_for(45.0) == 1
    assert canvas._sail_side_for(315.0) == -1

    app.quit()
