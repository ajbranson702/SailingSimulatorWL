from __future__ import annotations

from PySide6.QtCore import Qt
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
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from sailing_simulator.domain.models import Boat, BoatControlMode, RaceFormat, Vector2, WindMode, default_scenario
from sailing_simulator.domain.presets import adapt_course_to_format, add_gybe_mark, course_for_format
from sailing_simulator.domain.serialization import load_scenario, save_scenario
from sailing_simulator.domain.validation import validate_course
from sailing_simulator.ui.course_canvas import CourseCanvas


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.scenario = default_scenario()

        self.setWindowTitle("Sailing Race Simulator")
        self.resize(1180, 820)
        self.setCentralWidget(self._build_content())
        self._refresh_controls_from_scenario()
        self.statusBar().showMessage("Phase 2 course editor ready")

    def _build_content(self) -> QWidget:
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        self.canvas = CourseCanvas(self.scenario)
        self.canvas.scenario_changed.connect(self._on_canvas_changed)
        layout.addWidget(self.canvas, 1)
        layout.addWidget(self._build_control_panel())

        return root

    def _build_control_panel(self) -> QWidget:
        panel = QFrame()
        panel.setFrameShape(QFrame.Shape.StyledPanel)
        panel.setFixedWidth(320)

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
        form.addRow("Race format", self.format_combo)

        self.boat_count = QSpinBox()
        self.boat_count.setRange(1, 40)
        self.boat_count.setValue(len(self.scenario.boats))
        self.boat_count.valueChanged.connect(self._on_boat_count_changed)
        form.addRow("Boats", self.boat_count)

        self.wind_mode = QComboBox()
        for mode in WindMode:
            self.wind_mode.addItem(mode.value.replace("_", " ").title(), mode.value)
        self.wind_mode.currentIndexChanged.connect(self._update_scenario_from_controls)
        form.addRow("Wind mode", self.wind_mode)

        self.wind_strength = QDoubleSpinBox()
        self.wind_strength.setRange(0.0, 40.0)
        self.wind_strength.setSuffix(" kt")
        self.wind_strength.setValue(self.scenario.wind_model.base_speed_knots)
        self.wind_strength.valueChanged.connect(self._update_scenario_from_controls)
        form.addRow("Base wind", self.wind_strength)

        self.gust_percent = QDoubleSpinBox()
        self.gust_percent.setRange(0.0, 100.0)
        self.gust_percent.setSuffix(" %")
        self.gust_percent.setValue(self.scenario.wind_model.gust_percent)
        self.gust_percent.valueChanged.connect(self._update_scenario_from_controls)
        form.addRow("Gusts", self.gust_percent)

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
        mark_actions.addWidget(self.add_gybe_mark_button)
        layout.addLayout(mark_actions)

        file_actions = QHBoxLayout()
        save = QPushButton("Save")
        save.clicked.connect(self._save_scenario)
        load = QPushButton("Load")
        load.clicked.connect(self._load_scenario)
        file_actions.addWidget(save)
        file_actions.addWidget(load)
        layout.addLayout(file_actions)

        layout.addWidget(self._section_label("Playback"))

        playback = QHBoxLayout()
        playback.addWidget(QPushButton("Start"))
        playback.addWidget(QPushButton("Pause"))
        playback.addWidget(QPushButton("Reset"))
        layout.addLayout(playback)

        layout.addWidget(self._section_label("Boat Status"))
        self.status = QLabel(
            "Controlled boat: USER\n"
            "Heading: 315 deg\n"
            "Speed: 0.0 kt\n"
            "Current leg: pre-start"
        )
        self.status.setStyleSheet("font-family: Consolas, monospace;")
        layout.addWidget(self.status)

        layout.addStretch(1)

        note = QLabel("Drag marks or start-line endpoints on the course canvas.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #536471;")
        layout.addWidget(note)

        return panel

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("font-size: 14px; font-weight: 600; margin-top: 8px;")
        return label

    def _apply_selected_course_preset(self) -> None:
        race_format = self._selected_race_format()
        self.scenario.course = course_for_format(race_format)
        self.canvas.update()
        self._refresh_controls_from_scenario()
        self.statusBar().showMessage(f"Applied {race_format.value} course preset")

    def _on_course_format_changed(self) -> None:
        race_format = self._selected_race_format()
        adapt_course_to_format(self.scenario.course, race_format)
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
        path, _ = QFileDialog.getSaveFileName(self, "Save Scenario", "scenario.json", "Scenario JSON (*.json)")
        if not path:
            return

        save_scenario(self.scenario, path)
        self.statusBar().showMessage(f"Saved scenario to {path}")

    def _load_scenario(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load Scenario", "", "Scenario JSON (*.json)")
        if not path:
            return

        self.scenario = load_scenario(path)
        self.canvas.set_scenario(self.scenario)
        self._refresh_controls_from_scenario()
        self.statusBar().showMessage(f"Loaded scenario from {path}")

    def _on_canvas_changed(self) -> None:
        self.statusBar().showMessage("Course layout updated")

    def _on_boat_count_changed(self, count: int) -> None:
        self._set_boat_count(count)
        self.canvas.update()
        self._refresh_boat_status()

    def _update_scenario_from_controls(self) -> None:
        self.scenario.course.race_format = self._selected_race_format()
        self.scenario.wind_model.mode = self._selected_wind_mode()
        self.scenario.wind_model.base_speed_knots = self.wind_strength.value()
        self.scenario.wind_model.gust_percent = self.gust_percent.value()

    def _refresh_controls_from_scenario(self) -> None:
        self.format_combo.blockSignals(True)
        self.format_combo.setCurrentText(self.scenario.course.race_format.value)
        self.format_combo.blockSignals(False)
        self.boat_count.blockSignals(True)
        self.boat_count.setValue(len(self.scenario.boats))
        self.boat_count.blockSignals(False)
        self.wind_mode.setCurrentIndex(self.wind_mode.findData(self.scenario.wind_model.mode.value))
        self.wind_strength.setValue(self.scenario.wind_model.base_speed_knots)
        self.gust_percent.setValue(self.scenario.wind_model.gust_percent)
        self._refresh_course_controls()
        self._refresh_boat_status()

    def _refresh_course_controls(self) -> None:
        self.add_gybe_mark_button.setEnabled(self.scenario.course.race_format == RaceFormat.T3)

    def _refresh_boat_status(self) -> None:
        user_boat = next(
            (boat for boat in self.scenario.boats if boat.control_mode == BoatControlMode.USER),
            self.scenario.boats[0] if self.scenario.boats else None,
        )
        if user_boat is None:
            self.status.setText("No boats in scenario")
            return

        self.status.setText(
            f"Controlled boat: {user_boat.name}\n"
            f"Heading: {user_boat.heading_degrees:.0f} deg\n"
            f"Speed: {user_boat.speed_knots:.1f} kt\n"
            f"Course: {self.scenario.course.race_format.value}"
        )

    def _set_boat_count(self, count: int) -> None:
        boats = self.scenario.boats
        if not boats:
            boats.append(Boat("USER", Vector2(420.0, 735.0), 315.0, control_mode=BoatControlMode.USER))

        while len(boats) < count:
            index = len(boats)
            x = 420.0 + index * 42.0
            y = 735.0 + (index % 2) * 16.0
            boats.append(Boat(f"AI {index}", Vector2(x, y), 315.0))

        del boats[count:]
        if boats and all(boat.control_mode != BoatControlMode.USER for boat in boats):
            boats[0].control_mode = BoatControlMode.USER
            boats[0].name = "USER"

    def _selected_race_format(self) -> RaceFormat:
        return RaceFormat(self.format_combo.currentData())

    def _selected_wind_mode(self) -> WindMode:
        return WindMode(self.wind_mode.currentData())
