from PySide6.QtWidgets import QApplication

from sailing_simulator.domain.models import RaceFormat
from sailing_simulator.domain.presets import course_for_format
from sailing_simulator.ui.main_window import MainWindow


def test_t3_progress_table_shows_start_marks_and_finish():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.scenario.course = course_for_format(RaceFormat.T3)
    window._refresh_boat_status()

    headers = [
        window.progress_table.horizontalHeaderItem(column).text()
        for column in range(window.progress_table.columnCount())
    ]

    assert headers == ["Start", "W", "G", "L", "Finish"]

    window.close()
    app.quit()
