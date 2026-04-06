from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSplitter, QVBoxLayout, QWidget

from executor import CommandExecutor
from session import SessionState
from translator import CommandTranslator
from ui.terminal_pane import TerminalPane
from utils.qt import is_qobject_alive


class PaneManager(QWidget):
    def __init__(self, translator: CommandTranslator, executor: CommandExecutor, parent=None) -> None:
        super().__init__(parent)
        self._translator = translator
        self._executor = executor
        self.active_pane: TerminalPane | None = None

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(10, 10, 10, 10)
        self._layout.setSpacing(0)

        self.root_splitter = self._create_splitter(Qt.Horizontal)
        self._layout.addWidget(self.root_splitter)

        first_pane = self._create_pane()
        self.root_splitter.addWidget(first_pane)
        self.set_active_pane(first_pane)

    def _create_splitter(self, orientation: Qt.Orientation) -> QSplitter:
        splitter = QSplitter(orientation)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(6)
        splitter.setStyleSheet(
            """
            QSplitter::handle {
                background-color: #20242c;
            }
            QSplitter::handle:hover {
                background-color: #4ea1ff;
            }
            """
        )
        return splitter

    def _create_pane(self) -> TerminalPane:
        pane = TerminalPane(self._translator, self._executor, SessionState())
        pane.activated.connect(self.set_active_pane)
        pane.split_requested.connect(self.split_pane)
        pane.close_requested.connect(self.close_pane)
        pane.destroyed.connect(lambda _=None, pane_ref=pane: self._handle_pane_destroyed(pane_ref))
        return pane

    def set_active_pane(self, pane: TerminalPane | None) -> None:
        candidate = pane if self._is_valid_pane(pane) else self._find_first_pane(self.root_splitter)
        current = self.active_pane if self._is_valid_pane(self.active_pane) else None

        if candidate is None:
            self.active_pane = None
            return

        if current is candidate:
            candidate.set_active(True)
            self.active_pane = candidate
            return

        # Python can still hold a wrapper after Qt deleted the C++ pane, so every cross-pane call must validate first.
        if current is not None and self._is_valid_pane(current):
            current.set_active(False)

        self.active_pane = candidate
        if self._is_valid_pane(self.active_pane):
            self.active_pane.set_active(True)

    def focus_active_pane(self) -> None:
        if not self._is_valid_pane(self.active_pane):
            self.active_pane = self._find_first_pane(self.root_splitter)
        if self._is_valid_pane(self.active_pane):
            self.active_pane.focus_command_input()

    def split_active_horizontally(self) -> None:
        # Horizontal split means a horizontal divider, so panes stack top and bottom.
        self.split_active_pane(Qt.Vertical)

    def split_active_vertically(self) -> None:
        # Vertical split means a vertical divider, so panes appear side by side.
        self.split_active_pane(Qt.Horizontal)

    def split_active_pane(self, orientation: Qt.Orientation) -> None:
        if self._is_valid_pane(self.active_pane):
            self.split_pane(self.active_pane, orientation)

    def split_pane(self, pane: TerminalPane, orientation: Qt.Orientation) -> None:
        if not self._is_valid_pane(pane):
            return
        parent_splitter = pane.parentWidget()
        if not isinstance(parent_splitter, QSplitter) or not is_qobject_alive(parent_splitter):
            return

        new_pane = self._create_pane()
        index = parent_splitter.indexOf(pane)

        if parent_splitter.orientation() == orientation:
            parent_splitter.insertWidget(index + 1, new_pane)
            self._rebalance_splitter(parent_splitter)
        else:
            nested = self._create_splitter(orientation)
            pane.setParent(None)
            parent_splitter.insertWidget(index, nested)
            if not is_qobject_alive(nested):
                return
            nested.addWidget(pane)
            nested.addWidget(new_pane)
            self._rebalance_splitter(nested)
            self._rebalance_splitter(parent_splitter)

        # replaceWidget and splitter reshaping can reparent widgets; always activate the newly created valid pane.
        self.set_active_pane(new_pane)
        if self._is_valid_pane(new_pane):
            new_pane.focus_command_input()

    def close_active_pane(self) -> None:
        if self._is_valid_pane(self.active_pane):
            self.close_pane(self.active_pane)
        else:
            self.active_pane = self._find_first_pane(self.root_splitter)

    def close_pane(self, pane: TerminalPane) -> None:
        if not self._is_valid_pane(pane):
            return
        parent_splitter = pane.parentWidget()
        if not isinstance(parent_splitter, QSplitter) or not is_qobject_alive(parent_splitter):
            return

        if self._count_terminal_panes(self.root_splitter) <= 1:
            pane.append_info("At least one pane must remain open.")
            return

        next_pane = self._find_first_pane(self.root_splitter, exclude=pane)
        if self.active_pane is pane:
            self.set_active_pane(next_pane)
        elif not self._is_valid_pane(self.active_pane):
            self.active_pane = next_pane

        # Update manager references before scheduling deletion so no later focus/set_active touches the stale wrapper.
        pane.setParent(None)
        pane.deleteLater()
        self._collapse_splitter(parent_splitter)
        if not self._is_valid_pane(self.active_pane):
            self.active_pane = self._find_first_pane(self.root_splitter)
        self.set_active_pane(self.active_pane)
        self.focus_active_pane()

    def _count_terminal_panes(self, widget) -> int:
        if isinstance(widget, TerminalPane) and self._is_valid_pane(widget):
            return 1
        if isinstance(widget, QSplitter) and is_qobject_alive(widget):
            return sum(self._count_terminal_panes(widget.widget(i)) for i in range(widget.count()))
        return 0

    def _find_first_pane(self, widget, exclude: TerminalPane | None = None) -> TerminalPane | None:
        if isinstance(widget, TerminalPane) and self._is_valid_pane(widget) and widget is not exclude:
            return widget
        if isinstance(widget, QSplitter) and is_qobject_alive(widget):
            for index in range(widget.count()):
                found = self._find_first_pane(widget.widget(index), exclude=exclude)
                if found is not None:
                    return found
        return None

    def _collapse_splitter(self, splitter: QSplitter) -> None:
        if not is_qobject_alive(splitter):
            return
        if splitter.count() > 1:
            self._rebalance_splitter(splitter)
            return

        if splitter is self.root_splitter:
            child = splitter.widget(0)
            if isinstance(child, QSplitter) and is_qobject_alive(child):
                self._layout.removeWidget(self.root_splitter)
                self.root_splitter.setParent(None)
                self.root_splitter.deleteLater()
                self.root_splitter = child
                self._layout.addWidget(self.root_splitter)
            return

        parent = splitter.parentWidget()
        child = splitter.widget(0)
        if isinstance(parent, QSplitter) and is_qobject_alive(parent) and child is not None and is_qobject_alive(child):
            index = parent.indexOf(splitter)
            parent.replaceWidget(index, child)
            splitter.setParent(None)
            splitter.deleteLater()
            self._collapse_splitter(parent)

    def _rebalance_splitter(self, splitter: QSplitter) -> None:
        if not is_qobject_alive(splitter) or splitter.count() == 0:
            return
        splitter.setSizes([1] * splitter.count())

    def _handle_pane_destroyed(self, pane: TerminalPane) -> None:
        if self.active_pane is pane:
            self.active_pane = self._find_first_pane(self.root_splitter, exclude=pane)

    def _is_valid_pane(self, pane: TerminalPane | None) -> bool:
        return pane is not None and is_qobject_alive(pane)
