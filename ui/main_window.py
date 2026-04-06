from __future__ import annotations

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QMainWindow, QMessageBox

from executor import CommandExecutor
from quick_commands import QuickCommandsDialog, QuickCommandsManager, QuickCommandsStorage
from translator import CommandTranslator
from ui.workspace_tabs import WorkspaceTabs
from utils.qt import is_qobject_alive


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PSux")
        self.resize(1380, 860)
        self.setMinimumSize(1024, 680)

        translator = CommandTranslator()
        executor = CommandExecutor()
        self.workspace_tabs = WorkspaceTabs(translator, executor, self)
        self.quick_commands_manager = QuickCommandsManager(QuickCommandsStorage())
        self.setCentralWidget(self.workspace_tabs)
        self.workspace_tabs.quick_commands_requested.connect(self.open_quick_commands)

        self._install_shortcuts()
        self._apply_window_style()

    def _install_shortcuts(self) -> None:
        QShortcut(QKeySequence.Quit, self, activated=self.close)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.workspace_tabs.run_active)
        QShortcut(QKeySequence("Ctrl+Enter"), self, activated=self.workspace_tabs.run_active)
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.workspace_tabs.clear_active)
        QShortcut(QKeySequence("Ctrl+Shift+H"), self, activated=self.workspace_tabs.split_active_horizontally)
        QShortcut(QKeySequence("Ctrl+Shift+V"), self, activated=self.workspace_tabs.split_active_vertically)
        QShortcut(QKeySequence("Ctrl+Shift+P"), self, activated=self.open_quick_commands)
        QShortcut(QKeySequence("Ctrl+T"), self, activated=lambda: self.workspace_tabs.add_workspace())
        QShortcut(QKeySequence("Ctrl+W"), self, activated=self.workspace_tabs.close_current_workspace)

    def _apply_window_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background-color: #0c0f14;
            }
            QTabWidget::pane {
                border: none;
                top: -1px;
            }
            QTabBar::tab {
                background-color: #10141b;
                color: #b7c2cf;
                border: 1px solid #232b35;
                border-bottom: none;
                padding: 5px 11px;
                margin-right: 2px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }
            QTabBar::tab:selected {
                background-color: #151a23;
                color: #eef2f7;
                border-color: #35567d;
            }
            QTabBar::tab:hover {
                color: #eef2f7;
                border-color: #4b87c9;
            }
            QTabBar::close-button {
                image: none;
                subcontrol-position: right;
                width: 10px;
                height: 10px;
                margin-left: 6px;
                border-radius: 5px;
                background-color: #4a5360;
            }
            QTabBar::close-button:hover {
                background-color: #db6d69;
            }
            QTabWidget > QWidget {
                margin-top: 0px;
            }
            QToolButton {
                background-color: transparent;
                color: #9aa6b2;
                border: 1px solid #232b35;
                border-radius: 5px;
                padding: 2px 7px;
                min-width: 0px;
                min-height: 20px;
            }
            QToolButton:hover {
                color: #eef2f7;
                border-color: #4b87c9;
                background-color: #121722;
            }
            """
        )

    def open_quick_commands(self) -> None:
        dialog = QuickCommandsDialog(
            self.quick_commands_manager,
            insert_handler=self._insert_quick_command,
            execute_handler=self._execute_quick_command,
            parent=self,
        )
        dialog.exec()

    def _insert_quick_command(self, command: str) -> None:
        pane = self.workspace_tabs.active_pane
        if not is_qobject_alive(pane):
            QMessageBox.information(self, "Quick Commands", "Open or focus a terminal pane first.")
            return
        pane.set_command_text(command)

    def _execute_quick_command(self, command: str) -> None:
        pane = self.workspace_tabs.active_pane
        if not is_qobject_alive(pane):
            QMessageBox.information(self, "Quick Commands", "Open or focus a terminal pane first.")
            return
        pane.execute_command_text(command)
