from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from sailing_simulator.ui.main_window import MainWindow


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Sailing Race Simulator")
    app.setOrganizationName("Sailing Race Simulator")

    window = MainWindow()
    window.show()

    return app.exec()
