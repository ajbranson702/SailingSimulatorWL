from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from sailing_simulator.domain.models import BoatControlMode, Scenario, Vector2
from sailing_simulator.domain.wind import update_wind_field, wind_at


@dataclass(frozen=True)
class DragTarget:
    kind: str
    index: int | None = None


class CourseCanvas(QWidget):
    scenario_changed = Signal()
    key_pressed = Signal(int)

    def __init__(self, scenario: Scenario, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.scenario = scenario
        self._drag_target: DragTarget | None = None
        self.setMinimumSize(760, 720)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_scenario(self, scenario: Scenario) -> None:
        self.scenario = scenario
        self._drag_target = None
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(18, 18, -18, -18)
        painter.fillRect(self.rect(), QColor("#eef7fb"))
        painter.fillRect(rect, QColor("#d8f0f7"))

        self._draw_course_boundary(painter, rect)
        painter.save()
        painter.setClipRect(rect)
        self._draw_wind_grid(painter, rect)
        self._draw_course_objects(painter, rect)
        self._draw_tracks(painter, rect)
        self._draw_boats(painter, rect)
        painter.restore()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return

        target = self._hit_test(event.position())
        if target is None:
            return

        self._drag_target = target
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        self._move_drag_target(event.position())

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_target is not None:
            self._move_drag_target(event.position())
            return

        if self._hit_test(event.position()) is not None:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.unsetCursor()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._drag_target is not None:
            self._drag_target = None
            self.unsetCursor()
            self.scenario_changed.emit()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.isAutoRepeat():
            return
        self.key_pressed.emit(event.key())

    def _draw_course_boundary(self, painter: QPainter, rect: QRectF) -> None:
        painter.setPen(QPen(QColor("#4b6b75"), 2))
        painter.drawRect(rect)

        painter.setPen(QPen(QColor("#24576a"), 1))
        painter.setFont(QFont("Segoe UI", 10))
        painter.drawText(rect.adjusted(12, 10, -12, -12), Qt.AlignmentFlag.AlignTop, "Wind from top of screen")

    def _draw_wind_grid(self, painter: QPainter, rect: QRectF) -> None:
        field = self.scenario.wind_field
        if len(field.cells) != field.columns * field.rows:
            update_wind_field(self.scenario)

        for cell in field.cells:
            center = self._to_screen(cell.center, rect)
            length = 9.0 + min(cell.speed_knots, 25.0) * 0.7
            radians = math.radians(cell.direction_degrees + 180.0)
            end = QPointF(center.x() + math.sin(radians) * length, center.y() - math.cos(radians) * length)
            start = QPointF(center.x() - math.sin(radians) * length * 0.45, center.y() + math.cos(radians) * length * 0.45)
            alpha = max(75, min(210, int(70 + cell.speed_knots * 8)))
            color = QColor("#2d8aa8")
            color.setAlpha(alpha)
            painter.setPen(QPen(color, 1.4))
            painter.drawLine(start, end)
            self._draw_arrow_head(painter, end, radians, color)

    def _draw_course_objects(self, painter: QPainter, rect: QRectF) -> None:
        start = self.scenario.course.start_line
        pin = self._to_screen(start.pin, rect)
        committee = self._to_screen(start.committee_boat, rect)

        painter.setPen(QPen(QColor("#1f2933"), 4))
        painter.drawLine(pin, committee)
        painter.setPen(QPen(QColor("#1f2933"), 2))
        painter.setBrush(QColor("#f8fafc"))
        painter.drawEllipse(pin, 7, 7)
        painter.drawEllipse(committee, 7, 7)
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        painter.drawText(pin + QPointF(-14, -10), "PIN")
        painter.drawText(committee + QPointF(8, -10), "RC")

        painter.setPen(QPen(QColor("#9c6615"), 2))
        painter.setBrush(QColor("#f4b942"))
        for mark in self.scenario.course.marks:
            center = self._to_screen(mark.position, rect)
            painter.drawEllipse(center, 12, 12)
            painter.drawText(center + QPointF(14, 5), mark.label)

    def _draw_tracks(self, painter: QPainter, rect: QRectF) -> None:
        for boat in self.scenario.boats:
            if len(boat.track) < 2:
                continue

            color = QColor("#d64747") if boat.control_mode == BoatControlMode.USER else QColor("#2f6fe4")
            color.setAlpha(125)
            painter.setPen(QPen(color, 2))
            for first, second in zip(boat.track, boat.track[1:]):
                painter.drawLine(self._to_screen(first, rect), self._to_screen(second, rect))

    def _draw_boats(self, painter: QPainter, rect: QRectF) -> None:
        for boat in self.scenario.boats:
            center = self._to_screen(boat.position, rect)
            color = QColor("#e34848") if boat.control_mode == BoatControlMode.USER else QColor("#2f6fe4")
            painter.save()
            painter.translate(center)
            painter.rotate(boat.heading_degrees)
            self._draw_dinghy(painter, color, self._sail_side_for_boat(boat))
            painter.restore()

            painter.setPen(QPen(QColor("#1f2933"), 1))
            painter.drawText(center + QPointF(12, -8), boat.name)

    def _draw_dinghy(self, painter: QPainter, color: QColor, sail_side: int) -> None:
        hull = QPolygonF(
            [
                QPointF(0, -22),
                QPointF(8, -15),
                QPointF(11, 7),
                QPointF(7, 20),
                QPointF(-7, 20),
                QPointF(-11, 7),
                QPointF(-8, -15),
            ]
        )
        cockpit = QRectF(-5.5, -3.0, 11.0, 15.0)
        rudder = QPolygonF([QPointF(-3, 21), QPointF(3, 21), QPointF(2, 28), QPointF(-2, 28)])
        sail = QPolygonF([QPointF(0, -15), QPointF(0, 12), QPointF(13 * sail_side, 5)])
        boom_end = QPointF(14 * sail_side, 5)

        painter.setPen(QPen(QColor("#1f2933"), 1.25))
        painter.setBrush(QColor("#f8fafc"))
        painter.drawPolygon(hull)

        painter.setPen(QPen(color.darker(130), 1.5))
        painter.setBrush(color)
        painter.drawRoundedRect(cockpit, 3, 3)

        painter.setPen(QPen(QColor("#1f2933"), 1))
        painter.setBrush(QColor("#d7dde4"))
        painter.drawPolygon(rudder)

        painter.setPen(QPen(QColor("#1f2933"), 1))
        painter.drawLine(QPointF(0, -18), QPointF(0, 17))
        painter.drawLine(QPointF(0, 5), boom_end)

        painter.setPen(QPen(color.darker(140), 1))
        painter.setBrush(QColor(color.red(), color.green(), color.blue(), 75))
        painter.drawPolygon(sail)

    def _sail_side_for(self, heading_degrees: float) -> int:
        wind_from = self.scenario.wind_model.base_direction_degrees
        relative_wind = self._normalize_degrees(wind_from - heading_degrees)
        return -1 if relative_wind >= 0 else 1

    def _sail_side_for_boat(self, boat) -> int:
        wind_from, _ = wind_at(self.scenario, boat.position)
        relative_wind = self._normalize_degrees(wind_from - boat.heading_degrees)
        return -1 if relative_wind >= 0 else 1

    def _draw_arrow_head(self, painter: QPainter, end: QPointF, radians: float, color: QColor) -> None:
        left = QPointF(
            end.x() - math.sin(radians + 0.55) * 7.0,
            end.y() + math.cos(radians + 0.55) * 7.0,
        )
        right = QPointF(
            end.x() - math.sin(radians - 0.55) * 7.0,
            end.y() + math.cos(radians - 0.55) * 7.0,
        )
        painter.setBrush(color)
        painter.drawPolygon(QPolygonF([end, left, right]))

    def _normalize_degrees(self, degrees: float) -> float:
        return math.remainder(degrees, 360.0)

    def _hit_test(self, position: QPointF) -> DragTarget | None:
        rect = self._course_rect()
        start = self.scenario.course.start_line
        candidates: list[tuple[float, DragTarget]] = [
            (self._distance(position, self._to_screen(start.pin, rect)), DragTarget("pin")),
            (self._distance(position, self._to_screen(start.committee_boat, rect)), DragTarget("committee_boat")),
        ]

        for index, mark in enumerate(self.scenario.course.marks):
            candidates.append((self._distance(position, self._to_screen(mark.position, rect)), DragTarget("mark", index)))

        if self._can_drag_boats():
            for index, boat in enumerate(self.scenario.boats):
                candidates.append((self._distance(position, self._to_screen(boat.position, rect)), DragTarget("boat", index)))

        distance, target = min(candidates, key=lambda candidate: candidate[0])
        return target if distance <= 22.0 else None

    def _move_drag_target(self, position: QPointF) -> None:
        if self._drag_target is None:
            return

        course_point = self._to_course(position, self._course_rect())
        course = self.scenario.course
        if self._drag_target.kind == "pin":
            course.start_line.pin = course_point
        elif self._drag_target.kind == "committee_boat":
            course.start_line.committee_boat = course_point
        elif self._drag_target.kind == "mark" and self._drag_target.index is not None:
            course.marks[self._drag_target.index].position = course_point
        elif self._drag_target.kind == "boat" and self._drag_target.index is not None and self._can_drag_boats():
            boat = self.scenario.boats[self._drag_target.index]
            boat.position = course_point
            boat.speed_knots = 0.0
            boat.track = []

        self.update()

    def _can_drag_boats(self) -> bool:
        return (
            not self.scenario.race_state.is_running
            and self.scenario.race_state.elapsed_seconds == 0.0
            and all(not boat.has_started for boat in self.scenario.boats)
        )

    def _course_rect(self) -> QRectF:
        return QRectF(self.rect().adjusted(18, 18, -18, -18))

    def _to_screen(self, point, rect: QRectF) -> QPointF:
        course = self.scenario.course
        x = rect.left() + (point.x / course.boundary_width) * rect.width()
        y = rect.top() + (point.y / course.boundary_height) * rect.height()
        return QPointF(x, y)

    def _to_course(self, point: QPointF, rect: QRectF) -> Vector2:
        course = self.scenario.course
        x_ratio = self._clamp((point.x() - rect.left()) / rect.width(), 0.0, 1.0)
        y_ratio = self._clamp((point.y() - rect.top()) / rect.height(), 0.0, 1.0)
        return Vector2(x_ratio * course.boundary_width, y_ratio * course.boundary_height)

    def _distance(self, first: QPointF, second: QPointF) -> float:
        return math.hypot(first.x() - second.x(), first.y() - second.y())

    def _clamp(self, value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, value))
