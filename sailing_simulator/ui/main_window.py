from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from sailing_simulator.domain.models import RaceFormat, WindMode, default_scenario
from sailing_simulator.ui.course_canvas import CourseCanvas


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.scenario = default_scenario()

        self.setWindowTitle("Sailing Race Simulator")
        self.resize(1180, 820)
        self.setCentralWidget(self._build_content())
        self.statusBar().showMessage("Phase 1 shell ready")

    def _build_content(self) -> QWidget:
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        self.canvas = CourseCanvas(self.scenario)
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
        self.format_combo.addItems([race_format.value for race_format in RaceFormat])
        self.format_combo.setCurrentText(self.scenario.course.race_format.value)
        form.addRow("Race format", self.format_combo)

        self.boat_count = QSpinBox()
        self.boat_count.setRange(1, 40)
        self.boat_count.setValue(len(self.scenario.boats))
        form.addRow("Boats", self.boat_count)

        self.wind_mode = QComboBox()
        self.wind_mode.addItems([mode.value.replace("_", " ").title() for mode in WindMode])
        form.addRow("Wind mode", self.wind_mode)

        self.wind_strength = QDoubleSpinBox()
        self.wind_strength.setRange(0.0, 40.0)
        self.wind_strength.setSuffix(" kt")
        self.wind_strength.setValue(self.scenario.wind_model.base_speed_knots)
        form.addRow("Base wind", self.wind_strength)

        self.gust_percent = QDoubleSpinBox()
        self.gust_percent.setRange(0.0, 100.0)
        self.gust_percent.setSuffix(" %")
        self.gust_percent.setValue(self.scenario.wind_model.gust_percent)
        form.addRow("Gusts", self.gust_percent)

        layout.addLayout(form)
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

        note = QLabel("Phase 1: app shell, canvas, controls, and initial data model.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #536471;")
        layout.addWidget(note)

        return panel

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("font-size: 14px; font-weight: 600; margin-top: 8px;")
        return label
