from PySide6.QtWidgets import QApplication, QSizePolicy

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


def test_scenario_controls_keep_stable_widths():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()

    controls = [
        window.format_combo,
        window.boat_count,
        window.wind_mode,
        window.wind_strength,
        window.wind_direction,
        window.oscillation_amplitude,
        window.oscillation_period,
        window.persistent_shift,
        window.gust_percent,
        window.time_scale,
    ]

    assert all(control.minimumWidth() >= 170 for control in controls)
    assert all(control.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding for control in controls)
    assert window.status.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Ignored

    window.close()
    app.quit()
