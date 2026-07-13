from PySide6.QtWidgets import QApplication, QSizePolicy

from sailing_simulator.domain.models import RaceFormat, TerrainType
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


def test_terrain_controls_add_update_and_delete_terrain():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()

    assert window.scenario.terrain == []
    assert not window.delete_terrain_button.isEnabled()
    assert window.terrain_type.isEnabled()
    assert window.terrain_height.isEnabled()
    assert window.terrain_radius.isEnabled()

    window.terrain_type.setCurrentIndex(window.terrain_type.findData(TerrainType.TREES.value))
    window.terrain_height.setValue(55.0)
    window.terrain_radius.setValue(180.0)
    window._add_terrain()

    assert len(window.scenario.terrain) == 1
    assert window.scenario.terrain[0].terrain_type == TerrainType.TREES
    assert window.scenario.terrain[0].height == 55.0
    assert window.scenario.terrain[0].influence_radius == 180.0
    assert window.delete_terrain_button.isEnabled()

    window.terrain_type.setCurrentIndex(window.terrain_type.findData(TerrainType.CLIFF.value))
    window.terrain_height.setValue(70.0)
    window.terrain_radius.setValue(220.0)

    assert window.scenario.terrain[0].terrain_type == TerrainType.CLIFF
    assert window.scenario.terrain[0].height == 70.0
    assert window.scenario.terrain[0].influence_radius == 220.0
    assert window.selected_terrain_index == 0

    window._delete_selected_terrain()

    assert window.scenario.terrain == []
    assert not window.delete_terrain_button.isEnabled()

    window.close()
    app.quit()


def test_terrain_controls_edit_selected_terrain_only():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()

    window.terrain_type.setCurrentIndex(window.terrain_type.findData(TerrainType.HILL.value))
    window.terrain_height.setValue(45.0)
    window.terrain_radius.setValue(150.0)
    window._add_terrain()

    window.terrain_type.setCurrentIndex(window.terrain_type.findData(TerrainType.TREES.value))
    window.terrain_height.setValue(30.0)
    window.terrain_radius.setValue(100.0)
    window._add_terrain()

    assert len(window.scenario.terrain) == 2
    assert window.selected_terrain_index == 1

    window._on_terrain_selected(0)
    window.terrain_type.setCurrentIndex(window.terrain_type.findData(TerrainType.CLIFF.value))
    window.terrain_height.setValue(80.0)
    window.terrain_radius.setValue(250.0)

    assert window.scenario.terrain[0].terrain_type == TerrainType.CLIFF
    assert window.scenario.terrain[0].height == 80.0
    assert window.scenario.terrain[0].influence_radius == 250.0
    assert window.scenario.terrain[1].terrain_type == TerrainType.TREES
    assert window.scenario.terrain[1].height == 30.0
    assert window.scenario.terrain[1].influence_radius == 100.0

    window._delete_selected_terrain()

    assert len(window.scenario.terrain) == 1
    assert window.scenario.terrain[0].terrain_type == TerrainType.TREES
    assert window.selected_terrain_index == 0

    window.close()
    app.quit()
