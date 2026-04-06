from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QInputDialog, QTabWidget, QToolButton, QVBoxLayout, QWidget

from executor import CommandExecutor
from translator import CommandTranslator
from ui.pane_manager import PaneManager
from utils.qt import is_qobject_alive


class TerminalWorkspace(QWidget):
    def __init__(self, translator: CommandTranslator, executor: CommandExecutor, parent=None) -> None:
        super().__init__(parent)
        self.pane_manager = PaneManager(translator, executor, self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.pane_manager)


class WorkspaceTabs(QTabWidget):
    quick_commands_requested = Signal()

    def __init__(self, translator: CommandTranslator, executor: CommandExecutor, parent=None) -> None:
        super().__init__(parent)
        self._translator = translator
        self._executor = executor
        self._workspace_counter = 0

        self.setDocumentMode(True)
        self.setTabsClosable(True)
        self.setMovable(True)
        self.tabCloseRequested.connect(self.close_workspace)
        self.tabBarDoubleClicked.connect(self.rename_workspace)
        self.currentChanged.connect(lambda _: self.focus_active())

        corner = QWidget(self)
        corner_layout = QHBoxLayout(corner)
        corner_layout.setContentsMargins(0, 0, 0, 0)
        corner_layout.setSpacing(4)

        quick_button = QToolButton(corner)
        quick_button.setText("QC")
        quick_button.setToolTip("Quick Commands (Ctrl+Shift+P)")
        quick_button.setAutoRaise(True)
        quick_button.clicked.connect(self.quick_commands_requested.emit)

        add_button = QToolButton(corner)
        add_button.setText("+")
        add_button.setToolTip("New Tab (Ctrl+T)")
        add_button.setAutoRaise(True)
        add_button.clicked.connect(self.add_workspace)
        corner_layout.addWidget(quick_button)
        corner_layout.addWidget(add_button)

        self.setCornerWidget(corner, Qt.TopRightCorner)
        self._quick_button = quick_button
        self._add_button = add_button

        self.add_workspace()

    @property
    def active_pane(self):
        workspace = self.current_workspace()
        if workspace is None:
            return None
        return workspace.pane_manager.active_pane

    def current_workspace(self) -> TerminalWorkspace | None:
        widget = self.currentWidget()
        if isinstance(widget, TerminalWorkspace) and is_qobject_alive(widget):
            return widget
        return None

    def add_workspace(self, name: str | None = None) -> TerminalWorkspace:
        self._workspace_counter += 1
        workspace = TerminalWorkspace(self._translator, self._executor, self)
        label = name or f"Tab {self._workspace_counter}"
        index = self.addTab(workspace, label)
        self.setCurrentIndex(index)
        return workspace

    def close_workspace(self, index: int) -> None:
        if self.count() <= 1:
            return

        widget = self.widget(index)
        if widget is self.currentWidget():
            next_index = 0 if index != 0 else 1
            self.setCurrentIndex(next_index)

        self.removeTab(index)
        if widget is not None and is_qobject_alive(widget):
            widget.deleteLater()

    def rename_workspace(self, index: int) -> None:
        if index < 0 or index >= self.count():
            return
        current_name = self.tabText(index)
        new_name, accepted = QInputDialog.getText(self, "Rename Tab", "Tab name", text=current_name)
        if accepted and new_name.strip():
            self.setTabText(index, new_name.strip())

    def close_current_workspace(self) -> None:
        self.close_workspace(self.currentIndex())

    def run_active(self) -> None:
        pane = self.active_pane
        if is_qobject_alive(pane):
            pane.run_current_command()

    def clear_active(self) -> None:
        pane = self.active_pane
        if is_qobject_alive(pane):
            pane.clear_output()

    def split_active_horizontally(self) -> None:
        workspace = self.current_workspace()
        if workspace is not None:
            workspace.pane_manager.split_active_horizontally()

    def split_active_vertically(self) -> None:
        workspace = self.current_workspace()
        if workspace is not None:
            workspace.pane_manager.split_active_vertically()

    def focus_active(self) -> None:
        workspace = self.current_workspace()
        if workspace is not None:
            workspace.pane_manager.focus_active_pane()
