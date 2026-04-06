from __future__ import annotations

import sys

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


def build_application() -> QApplication:
    app = QApplication(sys.argv)
    app.setApplicationName("PSux")
    app.setOrganizationName("PSux")
    app.setStyle("Fusion")

    available_families = {family.lower(): family for family in QFontDatabase.families()}
    preferred_families = ["Cascadia Mono", "JetBrains Mono", "Consolas", "Courier New"]
    selected_family = next((available_families[name.lower()] for name in preferred_families if name.lower() in available_families), None)

    if selected_family:
        font = QFont(selected_family)
        font.setPointSize(10)
        app.setFont(font)
    return app


def main() -> int:
    app = build_application()
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
