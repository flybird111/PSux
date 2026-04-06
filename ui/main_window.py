from __future__ import annotations

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QMainWindow

from executor import CommandExecutor
from translator import CommandTranslator
from ui.pane_manager import PaneManager


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PSux")
        self.resize(1380, 860)
        self.setMinimumSize(1024, 680)

        translator = CommandTranslator()
        executor = CommandExecutor()
        self.pane_manager = PaneManager(translator, executor, self)
        self.setCentralWidget(self.pane_manager)

        self._install_shortcuts()
        self._apply_window_style()

    def _install_shortcuts(self) -> None:
        QShortcut(QKeySequence.Quit, self, activated=self.close)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._run_active)
        QShortcut(QKeySequence("Ctrl+Enter"), self, activated=self._run_active)
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self._clear_active)
        QShortcut(QKeySequence("Ctrl+Shift+H"), self, activated=self.pane_manager.split_active_horizontally)
        QShortcut(QKeySequence("Ctrl+Shift+V"), self, activated=self.pane_manager.split_active_vertically)
        QShortcut(QKeySequence("Ctrl+W"), self, activated=self.pane_manager.close_active_pane)

    def _apply_window_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background-color: #0c0f14;
            }
            """
        )

    def _run_active(self) -> None:
        pane = self.pane_manager.active_pane
        if pane is not None:
            pane.run_current_command()

    def _clear_active(self) -> None:
        pane = self.pane_manager.active_pane
        if pane is not None:
            pane.clear_output()
