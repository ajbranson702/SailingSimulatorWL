from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QSizePolicy

from sailing_simulator.domain.models import BoatControlMode, RaceFormat, TerrainObject, TerrainType, Vector2, default_scenario
from sailing_simulator.domain.presets import course_for_format
from sailing_simulator.domain.serialization import save_scenario
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
        window.start_sequence,
    ]

    assert all(control.minimumWidth() >= 170 for control in controls)
    assert all(control.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding for control in controls)
    assert window.status.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Ignored
    assert window.wind_direction.minimum() == -359.0
    assert window.wind_direction.maximum() == 359.0

    window.close()
    app.quit()


def test_negative_wind_direction_updates_scenario():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()

    window.wind_direction.setValue(-12.0)

    assert window.scenario.wind_model.base_direction_degrees == -12.0

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


def test_load_configuration_restores_terrain_and_selects_it(tmp_path):
    app = QApplication.instance() or QApplication([])
    scenario = default_scenario()
    scenario.terrain.append(TerrainObject(TerrainType.BUILDINGS, Vector2(660.0, 180.0), 75.0, 240.0))
    path = tmp_path / "terrain_config.json"
    save_scenario(scenario, path)

    window = MainWindow()
    window._load_scenario_from_path(str(path))

    assert len(window.scenario.terrain) == 1
    assert window.scenario.terrain[0].terrain_type == TerrainType.BUILDINGS
    assert window.scenario.terrain[0].position == Vector2(660.0, 180.0)
    assert window.scenario.terrain[0].height == 75.0
    assert window.scenario.terrain[0].influence_radius == 240.0
    assert window.selected_terrain_index == 0
    assert window.canvas.selected_terrain_index == 0
    assert window.delete_terrain_button.isEnabled()

    window.close()
    app.quit()


def test_start_button_begins_configured_countdown():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.start_sequence.setValue(180.0)

    window._start_simulation()

    assert window.scenario.race_state.is_running
    assert window.scenario.race_state.start_sequence_seconds == 180.0
    assert window.scenario.race_state.elapsed_seconds == -180.0
    assert "Countdown: 3:00" in window.status.text()

    window._pause_simulation()
    window.close()
    app.quit()


def test_g_key_gybes_user_boat():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    user_boat = next(boat for boat in window.scenario.boats if boat.control_mode == BoatControlMode.USER)
    user_boat.heading_degrees = 145.0
    user_boat.speed_knots = 6.0

    handled = window._handle_key(Qt.Key.Key_G)

    assert handled
    assert user_boat.heading_degrees == 235.0
    assert user_boat.speed_knots == 4.5

    window.close()
    app.quit()
