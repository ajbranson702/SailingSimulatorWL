from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from sailing_simulator.domain.models import BoatControlMode, Scenario


class CourseCanvas(QWidget):
    def __init__(self, scenario: Scenario, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.scenario = scenario
        self.setMinimumSize(760, 720)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(18, 18, -18, -18)
        painter.fillRect(self.rect(), QColor("#eef7fb"))
        painter.fillRect(rect, QColor("#d8f0f7"))

        self._draw_course_boundary(painter, rect)
        self._draw_wind_grid(painter, rect)
        self._draw_course_objects(painter, rect)
        self._draw_boats(painter, rect)

    def _draw_course_boundary(self, painter: QPainter, rect: QRectF) -> None:
        painter.setPen(QPen(QColor("#4b6b75"), 2))
        painter.drawRect(rect)

        painter.setPen(QPen(QColor("#24576a"), 1))
        painter.setFont(QFont("Segoe UI", 10))
        painter.drawText(rect.adjusted(12, 10, -12, -12), Qt.AlignmentFlag.AlignTop, "Wind from top of screen")

    def _draw_wind_grid(self, painter: QPainter, rect: QRectF) -> None:
        field = self.scenario.wind_field
        x_step = rect.width() / max(field.columns, 1)
        y_step = rect.height() / max(field.rows, 1)

        painter.setPen(QPen(QColor("#3f8ca7"), 1))
        for row in range(field.rows):
            for column in range(field.columns):
                x = rect.left() + column * x_step + x_step * 0.5
                y = rect.top() + row * y_step + y_step * 0.5
                painter.drawLine(QPointF(x, y - 14), QPointF(x, y + 14))
                painter.drawLine(QPointF(x, y + 14), QPointF(x - 5, y + 7))
                painter.drawLine(QPointF(x, y + 14), QPointF(x + 5, y + 7))

    def _draw_course_objects(self, painter: QPainter, rect: QRectF) -> None:
        start = self.scenario.course.start_line
        pin = self._to_screen(start.pin, rect)
        committee = self._to_screen(start.committee_boat, rect)

        painter.setPen(QPen(QColor("#1f2933"), 4))
        painter.drawLine(pin, committee)
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        painter.drawText(pin + QPointF(-14, -10), "PIN")
        painter.drawText(committee + QPointF(8, -10), "RC")

        painter.setPen(QPen(QColor("#9c6615"), 2))
        painter.setBrush(QColor("#f4b942"))
        for mark in self.scenario.course.marks:
            center = self._to_screen(mark.position, rect)
            painter.drawEllipse(center, 11, 11)
            painter.drawText(center + QPointF(14, 5), mark.label)

    def _draw_boats(self, painter: QPainter, rect: QRectF) -> None:
        for boat in self.scenario.boats:
            center = self._to_screen(boat.position, rect)
            color = QColor("#e34848") if boat.control_mode == BoatControlMode.USER else QColor("#2f6fe4")
            painter.save()
            painter.translate(center)
            painter.rotate(boat.heading_degrees)
            self._draw_dinghy(painter, color, self._sail_side_for(boat.heading_degrees))
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

    def _normalize_degrees(self, degrees: float) -> float:
        return math.remainder(degrees, 360.0)

    def _to_screen(self, point, rect: QRectF) -> QPointF:
        course = self.scenario.course
        x = rect.left() + (point.x / course.boundary_width) * rect.width()
        y = rect.top() + (point.y / course.boundary_height) * rect.height()
        return QPointF(x, y)
