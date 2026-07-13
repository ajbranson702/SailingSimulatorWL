from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from sailing_simulator.domain.models import (
    Boat,
    BoatControlMode,
    RaceFormat,
    TerrainObject,
    TerrainType,
    Vector2,
    WindMode,
    default_scenario,
)
from sailing_simulator.domain.presets import (
    adapt_course_to_format,
    add_gybe_mark,
    course_for_format,
    invalid_marks_for,
    remove_invalid_marks,
)
from sailing_simulator.domain.race_progress import ranked_boats, target_label_for, total_targets_for
from sailing_simulator.domain.serialization import load_scenario, save_scenario
from sailing_simulator.domain.simulation import (
    reset_boats_to_start,
    steer_away_from_wind,
    steer_toward_wind,
    step_scenario,
    tack,
    true_wind_angle,
)
from sailing_simulator.domain.validation import validate_course
from sailing_simulator.domain.wind import update_wind_field, wind_at
from sailing_simulator.ui.course_canvas import CourseCanvas


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.scenario = default_scenario()
        self.selected_terrain_index: int | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._step_simulation)

        self.setWindowTitle("Sailing Race Simulator")
        self.resize(1180, 820)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCentralWidget(self._build_content())
        self._refresh_controls_from_scenario()
        self.statusBar().showMessage("Phase 6 AI fleet controls ready")

    def _build_content(self) -> QWidget:
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        self.canvas = CourseCanvas(self.scenario)
        self.canvas.scenario_changed.connect(self._on_canvas_changed)
        self.canvas.key_pressed.connect(self._handle_key)
        self.canvas.terrain_selected.connect(self._on_terrain_selected)
        layout.addWidget(self.canvas, 1)
        layout.addWidget(self._build_control_panel())

        return root

    def _build_control_panel(self) -> QWidget:
        panel = QFrame()
        panel.setFrameShape(QFrame.Shape.StyledPanel)
        panel.setMinimumWidth(340)
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)

        title = QLabel("Scenario")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        layout.addWidget(title)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.format_combo = QComboBox()
        for race_format in RaceFormat:
            self.format_combo.addItem(race_format.value, race_format.value)
        self.format_combo.setCurrentText(self.scenario.course.race_format.value)
        self.format_combo.currentIndexChanged.connect(self._on_course_format_changed)
        self._stabilize_control(self.format_combo)
        form.addRow("Race format", self.format_combo)

        self.boat_count = QSpinBox()
        self.boat_count.setRange(1, 40)
        self.boat_count.setValue(len(self.scenario.boats))
        self.boat_count.valueChanged.connect(self._on_boat_count_changed)
        self._stabilize_control(self.boat_count)
        form.addRow("Boats", self.boat_count)

        self.wind_mode = QComboBox()
        for mode in WindMode:
            self.wind_mode.addItem(mode.value.replace("_", " ").title(), mode.value)
        self.wind_mode.currentIndexChanged.connect(self._update_scenario_from_controls)
        self._stabilize_control(self.wind_mode)
        form.addRow("Wind mode", self.wind_mode)

        self.wind_strength = QDoubleSpinBox()
        self.wind_strength.setRange(0.0, 40.0)
        self.wind_strength.setSuffix(" kt")
        self.wind_strength.setValue(self.scenario.wind_model.base_speed_knots)
        self.wind_strength.valueChanged.connect(self._update_scenario_from_controls)
        self._stabilize_control(self.wind_strength)
        form.addRow("Base wind", self.wind_strength)

        self.wind_direction = QDoubleSpinBox()
        self.wind_direction.setRange(0.0, 359.0)
        self.wind_direction.setSuffix(" deg")
        self.wind_direction.setValue(self.scenario.wind_model.base_direction_degrees)
        self.wind_direction.valueChanged.connect(self._update_scenario_from_controls)
        self._stabilize_control(self.wind_direction)
        form.addRow("Wind from", self.wind_direction)

        self.oscillation_amplitude = QDoubleSpinBox()
        self.oscillation_amplitude.setRange(0.0, 45.0)
        self.oscillation_amplitude.setSuffix(" deg")
        self.oscillation_amplitude.setValue(self.scenario.wind_model.oscillation_amplitude_degrees)
        self.oscillation_amplitude.valueChanged.connect(self._update_scenario_from_controls)
        self._stabilize_control(self.oscillation_amplitude)
        form.addRow("Oscillation", self.oscillation_amplitude)

        self.oscillation_period = QDoubleSpinBox()
        self.oscillation_period.setRange(10.0, 900.0)
        self.oscillation_period.setSuffix(" s")
        self.oscillation_period.setValue(self.scenario.wind_model.oscillation_period_seconds)
        self.oscillation_period.valueChanged.connect(self._update_scenario_from_controls)
        self._stabilize_control(self.oscillation_period)
        form.addRow("Osc period", self.oscillation_period)

        self.persistent_shift = QDoubleSpinBox()
        self.persistent_shift.setRange(0.0, 30.0)
        self.persistent_shift.setSuffix(" deg/min")
        self.persistent_shift.setValue(self.scenario.wind_model.persistent_shift_degrees_per_minute)
        self.persistent_shift.valueChanged.connect(self._update_scenario_from_controls)
        self._stabilize_control(self.persistent_shift)
        form.addRow("Shift rate", self.persistent_shift)

        self.gust_percent = QDoubleSpinBox()
        self.gust_percent.setRange(0.0, 100.0)
        self.gust_percent.setSuffix(" %")
        self.gust_percent.setValue(self.scenario.wind_model.gust_percent)
        self.gust_percent.valueChanged.connect(self._update_scenario_from_controls)
        self._stabilize_control(self.gust_percent)
        form.addRow("Gusts", self.gust_percent)

        self.time_scale = QDoubleSpinBox()
        self.time_scale.setRange(1.0, 50.0)
        self.time_scale.setSingleStep(1.0)
        self.time_scale.setDecimals(0)
        self.time_scale.setSuffix("x")
        self.time_scale.setValue(self.scenario.race_state.time_scale)
        self.time_scale.valueChanged.connect(self._update_scenario_from_controls)
        self._stabilize_control(self.time_scale)
        form.addRow("Sim speed", self.time_scale)

        layout.addLayout(form)
        layout.addWidget(self._section_label("Course"))

        course_actions = QHBoxLayout()
        apply_preset = QPushButton("Apply Preset")
        apply_preset.clicked.connect(self._apply_selected_course_preset)
        validate = QPushButton("Validate")
        validate.clicked.connect(self._validate_course)
        course_actions.addWidget(apply_preset)
        course_actions.addWidget(validate)
        layout.addLayout(course_actions)

        mark_actions = QHBoxLayout()
        self.add_gybe_mark_button = QPushButton("Add Gybe Mark")
        self.add_gybe_mark_button.clicked.connect(self._add_gybe_mark)
        self.delete_invalid_marks_button = QPushButton("Delete Invalid Marks")
        self.delete_invalid_marks_button.clicked.connect(self._delete_invalid_marks)
        mark_actions.addWidget(self.add_gybe_mark_button)
        mark_actions.addWidget(self.delete_invalid_marks_button)
        layout.addLayout(mark_actions)

        file_actions = QHBoxLayout()
        save = QPushButton("Save Config")
        save.clicked.connect(self._save_scenario)
        load = QPushButton("Load Config")
        load.clicked.connect(self._load_scenario)
        file_actions.addWidget(save)
        file_actions.addWidget(load)
        layout.addLayout(file_actions)

        layout.addWidget(self._section_label("Terrain"))

        terrain_form = QFormLayout()
        terrain_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.terrain_type = QComboBox()
        for terrain_type in TerrainType:
            self.terrain_type.addItem(terrain_type.value.title(), terrain_type.value)
        self.terrain_type.currentIndexChanged.connect(self._update_selected_terrain_from_controls)
        self._stabilize_control(self.terrain_type)
        terrain_form.addRow("Type", self.terrain_type)

        self.terrain_height = QDoubleSpinBox()
        self.terrain_height.setRange(0.0, 100.0)
        self.terrain_height.setSuffix(" m")
        self.terrain_height.setValue(45.0)
        self.terrain_height.valueChanged.connect(self._update_selected_terrain_from_controls)
        self._stabilize_control(self.terrain_height)
        terrain_form.addRow("Height", self.terrain_height)

        self.terrain_radius = QDoubleSpinBox()
        self.terrain_radius.setRange(25.0, 350.0)
        self.terrain_radius.setSuffix(" u")
        self.terrain_radius.setValue(150.0)
        self.terrain_radius.valueChanged.connect(self._update_selected_terrain_from_controls)
        self._stabilize_control(self.terrain_radius)
        terrain_form.addRow("Radius", self.terrain_radius)
        layout.addLayout(terrain_form)

        terrain_actions = QHBoxLayout()
        self.add_terrain_button = QPushButton("Add Terrain")
        self.add_terrain_button.clicked.connect(self._add_terrain)
        self.delete_terrain_button = QPushButton("Delete Terrain")
        self.delete_terrain_button.clicked.connect(self._delete_selected_terrain)
        terrain_actions.addWidget(self.add_terrain_button)
        terrain_actions.addWidget(self.delete_terrain_button)
        layout.addLayout(terrain_actions)

        layout.addWidget(self._section_label("Playback"))

        playback = QHBoxLayout()
        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self._start_simulation)
        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self._pause_simulation)
        self.reset_button = QPushButton("Reset")
        self.reset_button.clicked.connect(self._reset_simulation)
        playback.addWidget(self.start_button)
        playback.addWidget(self.pause_button)
        playback.addWidget(self.reset_button)
        layout.addLayout(playback)

        layout.addWidget(self._section_label("Boat Status"))
        self.status = QLabel(
            "Controlled boat: USER\n"
            "Heading: 315 deg\n"
            "Speed: 0.0 kt\n"
            "Current leg: pre-start"
        )
        self.status.setStyleSheet("font-family: Consolas, monospace;")
        self.status.setMinimumWidth(0)
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.status)

        layout.addWidget(self._section_label("Course Progress"))
        self.progress_table = QTableWidget()
        self.progress_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.progress_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.progress_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.progress_table.setMinimumHeight(118)
        self.progress_table.setMaximumHeight(190)
        self.progress_table.verticalHeader().setVisible(True)
        self.progress_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.progress_table)

        layout.addStretch(1)

        note = QLabel("Before starting, drag boats, terrain, marks, or start-line endpoints on the course canvas.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #536471;")
        layout.addWidget(note)

        scroll = QScrollArea()
        scroll.setWidget(panel)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFixedWidth(360)
        scroll.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        return scroll

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("font-size: 14px; font-weight: 600; margin-top: 8px;")
        return label

    def _stabilize_control(self, control: QWidget) -> None:
        control.setMinimumWidth(170)
        control.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.isAutoRepeat():
            return

        if not self._handle_key(event.key()):
            super().keyPressEvent(event)

    def _handle_key(self, key: int) -> bool:
        user_boat = self._user_boat()
        if user_boat is None:
            return False

        wind_from, _ = wind_at(self.scenario, user_boat.position)
        if key == Qt.Key.Key_Up:
            steer_toward_wind(user_boat, wind_from, 5.0)
        elif key == Qt.Key.Key_Down:
            steer_away_from_wind(user_boat, wind_from, 5.0)
        elif key == Qt.Key.Key_T:
            tack(user_boat, wind_from)
        else:
            return False

        self.canvas.update()
        self._refresh_boat_status()
        return True

    def _apply_selected_course_preset(self) -> None:
        race_format = self._selected_race_format()
        self.scenario.course = course_for_format(race_format)
        reset_boats_to_start(self.scenario)
        self.canvas.update()
        self._refresh_controls_from_scenario()
        self.statusBar().showMessage(f"Applied {race_format.value} course preset")

    def _on_course_format_changed(self) -> None:
        race_format = self._selected_race_format()
        adapt_course_to_format(self.scenario.course, race_format)
        reset_boats_to_start(self.scenario)
        self.canvas.update()
        self._refresh_course_controls()
        self._refresh_boat_status()
        self.statusBar().showMessage(f"Course format set to {race_format.value}")

    def _add_gybe_mark(self) -> None:
        adapt_course_to_format(self.scenario.course, RaceFormat.T3)
        add_gybe_mark(self.scenario.course)
        self.format_combo.setCurrentText(RaceFormat.T3.value)
        self.canvas.update()
        self._refresh_course_controls()
        self._refresh_boat_status()
        self.statusBar().showMessage("Gybe mark added for T course")

    def _delete_invalid_marks(self) -> None:
        removed = remove_invalid_marks(self.scenario.course)
        self.canvas.update()
        self._refresh_course_controls()
        self.statusBar().showMessage(f"Deleted {len(removed)} invalid mark(s)")

    def _validate_course(self) -> None:
        self._update_scenario_from_controls()
        errors = validate_course(self.scenario.course)
        if errors:
            QMessageBox.warning(self, "Course Validation", "\n".join(errors))
            self.statusBar().showMessage("Course validation failed")
        else:
            QMessageBox.information(self, "Course Validation", "Course is ready to race.")
            self.statusBar().showMessage("Course validation passed")

    def _save_scenario(self) -> None:
        self._update_scenario_from_controls()
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Configuration",
            "sailing_configuration.json",
            "Sailing Configuration (*.json)",
        )
        if not path:
            return

        self._save_scenario_to_path(path)

    def _load_scenario(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load Configuration", "", "Sailing Configuration (*.json)")
        if not path:
            return

        self._load_scenario_from_path(path)

    def _save_scenario_to_path(self, path: str) -> None:
        self._update_scenario_from_controls()
        save_scenario(self.scenario, path)
        self.statusBar().showMessage(f"Saved configuration to {path}")

    def _load_scenario_from_path(self, path: str) -> None:
        self.scenario = load_scenario(path)
        self.scenario.race_state.is_running = False
        update_wind_field(self.scenario)
        self.canvas.set_scenario(self.scenario)
        self._set_selected_terrain_index(0 if self.scenario.terrain else None)
        self._refresh_controls_from_scenario()
        self.statusBar().showMessage(f"Loaded configuration from {path}")

    def _on_canvas_changed(self) -> None:
        update_wind_field(self.scenario)
        self._refresh_terrain_controls()
        self._refresh_boat_status()
        self.statusBar().showMessage("Scenario layout updated")

    def _on_terrain_selected(self, index: int) -> None:
        self._set_selected_terrain_index(index if index >= 0 else None)
        self._refresh_terrain_controls()
        if self.selected_terrain_index is None:
            self.statusBar().showMessage("Terrain selection cleared")
        else:
            self.statusBar().showMessage(f"Selected terrain {self.selected_terrain_index + 1}")

    def _on_boat_count_changed(self, count: int) -> None:
        self._set_boat_count(count)
        self.canvas.update()
        self._refresh_boat_status()

    def _start_simulation(self) -> None:
        self._update_scenario_from_controls()
        self.scenario.race_state.is_running = True
        self._timer.start()
        self.canvas.setFocus()
        self.statusBar().showMessage("Simulation running")

    def _pause_simulation(self) -> None:
        self.scenario.race_state.is_running = False
        self._timer.stop()
        self.statusBar().showMessage("Simulation paused")

    def _reset_simulation(self) -> None:
        self._pause_simulation()
        reset_boats_to_start(self.scenario)
        self.canvas.update()
        self._refresh_boat_status()
        self.statusBar().showMessage("Simulation reset")

    def _step_simulation(self) -> None:
        self._update_scenario_from_controls()
        elapsed_seconds = (self._timer.interval() / 1000.0) * self.scenario.race_state.time_scale
        step_scenario(self.scenario, elapsed_seconds)
        self.canvas.update()
        self._refresh_boat_status()

    def _update_scenario_from_controls(self) -> None:
        self.scenario.course.race_format = self._selected_race_format()
        self.scenario.wind_model.mode = self._selected_wind_mode()
        self.scenario.wind_model.base_speed_knots = self.wind_strength.value()
        self.scenario.wind_model.base_direction_degrees = self.wind_direction.value()
        self.scenario.wind_model.oscillation_amplitude_degrees = self.oscillation_amplitude.value()
        self.scenario.wind_model.oscillation_period_seconds = self.oscillation_period.value()
        self.scenario.wind_model.persistent_shift_degrees_per_minute = self.persistent_shift.value()
        self.scenario.wind_model.gust_percent = self.gust_percent.value()
        self.scenario.race_state.time_scale = self.time_scale.value()
        update_wind_field(self.scenario)
        self.canvas.update()

    def _refresh_controls_from_scenario(self) -> None:
        self.format_combo.blockSignals(True)
        self.format_combo.setCurrentText(self.scenario.course.race_format.value)
        self.format_combo.blockSignals(False)
        self.boat_count.blockSignals(True)
        self.boat_count.setValue(len(self.scenario.boats))
        self.boat_count.blockSignals(False)
        self.wind_mode.setCurrentIndex(self.wind_mode.findData(self.scenario.wind_model.mode.value))
        self.wind_strength.setValue(self.scenario.wind_model.base_speed_knots)
        self.wind_direction.setValue(self.scenario.wind_model.base_direction_degrees)
        self.oscillation_amplitude.setValue(self.scenario.wind_model.oscillation_amplitude_degrees)
        self.oscillation_period.setValue(self.scenario.wind_model.oscillation_period_seconds)
        self.persistent_shift.setValue(self.scenario.wind_model.persistent_shift_degrees_per_minute)
        self.gust_percent.setValue(self.scenario.wind_model.gust_percent)
        self.time_scale.setValue(self.scenario.race_state.time_scale)
        self._refresh_course_controls()
        if self._selected_terrain() is None:
            self._set_selected_terrain_index(None)
        self._refresh_terrain_controls()
        self._refresh_boat_status()

    def _refresh_course_controls(self) -> None:
        self.add_gybe_mark_button.setEnabled(self.scenario.course.race_format == RaceFormat.T3)
        self.delete_invalid_marks_button.setEnabled(bool(invalid_marks_for(self.scenario.course)))

    def _refresh_terrain_controls(self) -> None:
        terrain = self._selected_terrain()
        has_terrain = terrain is not None
        self.delete_terrain_button.setEnabled(has_terrain)
        if terrain is None:
            return

        self.terrain_type.blockSignals(True)
        self.terrain_type.setCurrentIndex(self.terrain_type.findData(terrain.terrain_type.value))
        self.terrain_type.blockSignals(False)
        self.terrain_height.blockSignals(True)
        self.terrain_height.setValue(terrain.height)
        self.terrain_height.blockSignals(False)
        self.terrain_radius.blockSignals(True)
        self.terrain_radius.setValue(terrain.influence_radius)
        self.terrain_radius.blockSignals(False)

    def _selected_terrain(self) -> TerrainObject | None:
        if self.selected_terrain_index is None:
            return None
        if not 0 <= self.selected_terrain_index < len(self.scenario.terrain):
            return None
        return self.scenario.terrain[self.selected_terrain_index]

    def _set_selected_terrain_index(self, index: int | None) -> None:
        if index is None or index < 0 or index >= len(self.scenario.terrain):
            self.selected_terrain_index = None
        else:
            self.selected_terrain_index = index
        self.canvas.select_terrain(self.selected_terrain_index)

    def _add_terrain(self) -> None:
        terrain = TerrainObject(
            terrain_type=TerrainType(self.terrain_type.currentData() or TerrainType.HILL.value),
            position=Vector2(self.scenario.course.boundary_width * 0.35, self.scenario.course.boundary_height * 0.35),
            height=self.terrain_height.value(),
            influence_radius=self.terrain_radius.value(),
        )
        self.scenario.terrain.append(terrain)
        self._set_selected_terrain_index(len(self.scenario.terrain) - 1)
        update_wind_field(self.scenario)
        self.canvas.update()
        self._refresh_terrain_controls()
        self.statusBar().showMessage("Terrain added")

    def _delete_selected_terrain(self) -> None:
        if self.selected_terrain_index is None or not 0 <= self.selected_terrain_index < len(self.scenario.terrain):
            return
        deleted_index = self.selected_terrain_index
        self.scenario.terrain.pop(deleted_index)
        next_index = min(deleted_index, len(self.scenario.terrain) - 1) if self.scenario.terrain else None
        self._set_selected_terrain_index(next_index)
        update_wind_field(self.scenario)
        self.canvas.update()
        self._refresh_terrain_controls()
        self.statusBar().showMessage("Terrain deleted")

    def _update_selected_terrain_from_controls(self) -> None:
        terrain = self._selected_terrain()
        if terrain is None:
            return
        terrain.terrain_type = TerrainType(self.terrain_type.currentData())
        terrain.height = self.terrain_height.value()
        terrain.influence_radius = self.terrain_radius.value()
        update_wind_field(self.scenario)
        self.canvas.update()

    def _refresh_boat_status(self) -> None:
        user_boat = self._user_boat()
        if user_boat is None:
            self.status.setText("No boats in scenario")
            self._refresh_progress_table()
            return

        local_wind_direction, local_wind_speed = wind_at(self.scenario, user_boat.position)
        twa = true_wind_angle(user_boat.heading_degrees, local_wind_direction)
        progress_text = self._boat_progress_text(user_boat)
        self.status.setText(
            f"Controlled boat: {user_boat.name}\n"
            f"Heading: {user_boat.heading_degrees:.0f} deg\n"
            f"Speed: {user_boat.speed_knots:.1f} kt\n"
            f"Wind: {local_wind_direction:.0f} deg / {local_wind_speed:.1f} kt\n"
            f"TWA: {twa:.0f} deg\n"
            f"Sim speed: {self.scenario.race_state.time_scale:.0f}x\n"
            f"Elapsed: {self.scenario.race_state.elapsed_seconds:.1f} s\n"
            f"Course: {self.scenario.course.race_format.value}\n"
            f"{progress_text}\n"
            f"{self._rankings_text()}\n"
            f"{self._event_status_text()}"
        )
        self._refresh_progress_table()

    def _refresh_progress_table(self) -> None:
        headers = ["Start"]
        headers.extend(target_label_for(self.scenario.course, index) for index in range(total_targets_for(self.scenario.course)))
        headers.append("Finish")
        self.progress_table.setColumnCount(len(headers))
        self.progress_table.setRowCount(len(self.scenario.boats))
        self.progress_table.setHorizontalHeaderLabels(headers)
        self.progress_table.setVerticalHeaderLabels([boat.name for boat in self.scenario.boats])

        finish_column = len(headers) - 1
        for row, boat in enumerate(self.scenario.boats):
            start_item = QTableWidgetItem("✓" if boat.has_started or boat.is_finished else "")
            start_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.progress_table.setItem(row, 0, start_item)

            for column in range(1, finish_column):
                target_index = column - 1
                item = QTableWidgetItem("✓" if boat.target_leg_index > target_index or boat.is_finished else "")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.progress_table.setItem(row, column, item)

            finish_item = QTableWidgetItem("✓" if boat.is_finished else "")
            finish_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.progress_table.setItem(row, finish_column, finish_item)

        self.progress_table.resizeColumnsToContents()

    def _set_boat_count(self, count: int) -> None:
        boats = self.scenario.boats
        if not boats:
            boats.append(Boat("USER", Vector2(420.0, 735.0), 315.0, control_mode=BoatControlMode.USER))

        while len(boats) < count:
            index = len(boats)
            x = 390.0 + index * 70.0
            y = 790.0 + (index % 2) * 16.0
            boats.append(Boat(f"AI {index}", Vector2(x, y), 315.0))

        del boats[count:]
        if boats and all(boat.control_mode != BoatControlMode.USER for boat in boats):
            boats[0].control_mode = BoatControlMode.USER
            boats[0].name = "USER"

    def _user_boat(self) -> Boat | None:
        return next(
            (boat for boat in self.scenario.boats if boat.control_mode == BoatControlMode.USER),
            self.scenario.boats[0] if self.scenario.boats else None,
        )

    def _boat_progress_text(self, boat: Boat) -> str:
        if boat.is_finished and boat.finish_time_seconds is not None:
            return f"Finished: {boat.finish_time_seconds:.1f} s"
        if not boat.has_started:
            return "Target: start"

        total_targets = total_targets_for(self.scenario.course)
        next_target = target_label_for(self.scenario.course, boat.target_leg_index)
        return f"Target: {next_target} ({boat.target_leg_index}/{total_targets})"

    def _event_status_text(self) -> str:
        if self.scenario.race_state.events:
            return "\n".join(event.message for event in self.scenario.race_state.events[-3:])
        if self.scenario.race_state.finished_boats:
            finished = ", ".join(sorted(self.scenario.race_state.finished_boats))
            return f"Finished: {finished}"
        return "Events: none"

    def _rankings_text(self) -> str:
        ranked = ranked_boats(self.scenario.course, self.scenario.boats)
        entries = [f"{index + 1}. {boat.name}" for index, boat in enumerate(ranked[:5])]
        if not entries:
            return "Rankings: none"
        return "Rankings: " + " | ".join(entries)

    def _selected_race_format(self) -> RaceFormat:
        return RaceFormat(self.format_combo.currentData())

    def _selected_wind_mode(self) -> WindMode:
        return WindMode(self.wind_mode.currentData())
