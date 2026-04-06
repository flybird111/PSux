from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QFocusEvent, QKeyEvent, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QTextEdit, QVBoxLayout, QWidget

from history import CommandHistory
from utils.completion import CompletionOutcome
from utils.qt import is_qobject_alive


class HistoryLineEdit(QLineEdit):
    execute_requested = Signal()
    focus_received = Signal()
    completion_candidates_requested = Signal(object)

    def __init__(
        self,
        history: CommandHistory,
        completion_provider: Callable[[str, int, bool], CompletionOutcome | None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._history = history
        self._completion_provider = completion_provider
        self._last_tab_state: tuple[str, int, tuple[str, ...]] | None = None

    def focusInEvent(self, event: QFocusEvent) -> None:
        super().focusInEvent(event)
        self.focus_received.emit()

    def event(self, event) -> bool:
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Tab:
            self._handle_completion()
            return True
        return super().event(event)

    def focusNextPrevChild(self, next: bool) -> bool:
        # Terminal-style Tab should stay inside the command line instead of moving focus.
        return False

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in {Qt.Key_Return, Qt.Key_Enter} and not (event.modifiers() & Qt.ControlModifier):
            self._reset_completion_state()
            self.execute_requested.emit()
            return
        if event.key() == Qt.Key_Up:
            self._reset_completion_state()
            self.setText(self._history.previous(self.text()))
            return
        if event.key() == Qt.Key_Down:
            self._reset_completion_state()
            self.setText(self._history.next())
            return
        self._reset_completion_state()
        super().keyPressEvent(event)

    def _handle_completion(self) -> None:
        if self._completion_provider is None or not is_qobject_alive(self):
            return

        text = self.text()
        cursor = self.cursorPosition()
        repeated = self._last_tab_state is not None and self._last_tab_state[:2] == (text, cursor)
        outcome = self._completion_provider(text, cursor, repeated)
        if outcome is None:
            self._last_tab_state = None
            return

        if not is_qobject_alive(self):
            return

        if outcome.text != text:
            self.setText(outcome.text)
            self.setCursorPosition(outcome.cursor_position)
        if outcome.displayed and outcome.candidates:
            self.completion_candidates_requested.emit(outcome.candidates)

        candidate_key = tuple(outcome.candidates)
        self._last_tab_state = (self.text(), self.cursorPosition(), candidate_key)

    def _reset_completion_state(self) -> None:
        self._last_tab_state = None


class TerminalTranscript(QTextEdit):
    clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setAcceptRichText(False)
        self.setLineWrapMode(QTextEdit.NoWrap)
        self.setFrameStyle(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        self.clicked.emit()

    def append_segments(self, segments: list[tuple[str, str]]) -> None:
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        for text, color in segments:
            if not text:
                continue
            format_ = QTextCharFormat()
            format_.setForeground(QColor(color))
            cursor.insertText(text, format_)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def append_block(self, text: str, color: str) -> None:
        if not text:
            return
        normalized = text if text.endswith("\n") else f"{text}\n"
        self.append_segments([(normalized, color)])

    def append_stream(self, text: str, color: str) -> None:
        if not text:
            return
        self.append_segments([(text, color)])

    def append_command(self, prompt_parts: tuple[str, str, str], command: str) -> None:
        app_name, path_text, marker = prompt_parts
        self.append_segments(
            [
                (app_name, "#67d4ff"),
                (":", "#98a4b3"),
                (path_text, "#9be38c"),
                (marker, "#f7b955"),
                (" ", "#98a4b3"),
                (command, "#f8fafc"),
                ("\n", "#f8fafc"),
            ]
        )

    def append_error(self, text: str) -> None:
        self.append_block(text, "#ff8e7c")

    def append_output(self, text: str) -> None:
        self.append_block(text, "#eef2f7")

    def append_info(self, text: str) -> None:
        self.append_block(text, "#8fbafc")

    def append_stream_output(self, text: str) -> None:
        self.append_stream(text, "#eef2f7")

    def append_stream_error(self, text: str) -> None:
        self.append_stream(text, "#ff8e7c")


class TerminalView(QWidget):
    activated = Signal()
    execute_requested = Signal()
    completion_candidates_requested = Signal(object)

    def __init__(
        self,
        history: CommandHistory,
        completion_provider: Callable[[str, int, bool], CompletionOutcome | None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.transcript = TerminalTranscript()
        self.prompt_label = QLabel()
        self.prompt_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.input = HistoryLineEdit(history, completion_provider=completion_provider)
        self.input.execute_requested.connect(self.execute_requested.emit)
        self.input.focus_received.connect(self.activated.emit)
        self.input.completion_candidates_requested.connect(self.completion_candidates_requested.emit)
        self.transcript.clicked.connect(self.focus_input)
        self.prompt_label.setTextFormat(Qt.RichText)

        self._build_layout()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(0)

        prompt_row = QWidget()
        prompt_row.setObjectName("promptRow")
        prompt_layout = QHBoxLayout(prompt_row)
        prompt_layout.setContentsMargins(0, 6, 0, 0)
        prompt_layout.setSpacing(8)
        prompt_layout.addWidget(self.prompt_label, 0)
        prompt_layout.addWidget(self.input, 1)

        root.addWidget(self.transcript, 1)
        root.addWidget(prompt_row, 0)

        self.setObjectName("terminalView")
        self.setStyleSheet(
            """
            QWidget#terminalView {
                background-color: #11131a;
                border: 1px solid #262c35;
                border-radius: 10px;
            }
            QWidget#promptRow {
                background-color: #11131a;
            }
            QTextEdit {
                background-color: #11131a;
                color: #eef2f7;
                border: none;
                padding: 0px;
                selection-background-color: #285f8f;
            }
            QLabel {
                color: #67d4ff;
                padding: 0px;
            }
            QLineEdit {
                background-color: #11131a;
                color: #f8fafc;
                border: none;
                padding: 0px;
                selection-background-color: #285f8f;
            }
            """
        )

    def set_prompt_parts(self, prompt_parts: tuple[str, str, str]) -> None:
        if not is_qobject_alive(self.prompt_label):
            return
        app_name, path_text, marker = prompt_parts
        self.prompt_label.setText(
            f"<span style='color:#67d4ff'>{app_name}</span>"
            f"<span style='color:#98a4b3'>:</span>"
            f"<span style='color:#9be38c'>{path_text}</span>"
            f"<span style='color:#f7b955'>{marker}</span>"
        )

    def current_command(self) -> str:
        if not is_qobject_alive(self.input):
            return ""
        return self.input.text()

    def clear_command(self) -> None:
        if is_qobject_alive(self.input):
            self.input.clear()

    def clear_transcript(self) -> None:
        if is_qobject_alive(self.transcript):
            self.transcript.clear()

    def focus_input(self) -> None:
        if not is_qobject_alive(self.input):
            return
        self.input.setFocus(Qt.ShortcutFocusReason)
        if is_qobject_alive(self.input):
            self.input.deselect()
        self.activated.emit()

    def set_busy(self, busy: bool) -> None:
        if is_qobject_alive(self.input):
            self.input.setEnabled(not busy)
