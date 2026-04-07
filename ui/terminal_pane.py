from __future__ import annotations

from collections import deque

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from executor import CommandExecutor, CommandWorker, ExecutionResult
from session import SessionState
from translator import CommandTranslator
from ui.widgets import TerminalView
from utils.completion import CompletionEngine
from utils.path_utils import build_prompt_parts
from utils.errors import UserFacingError
from utils.qt import is_qobject_alive


class TerminalPane(QFrame):
    activated = Signal(object)
    split_requested = Signal(object, object)
    close_requested = Signal(object)

    def __init__(self, translator: CommandTranslator, executor: CommandExecutor, session: SessionState | None = None, parent=None) -> None:
        super().__init__(parent)
        self._translator = translator
        self._executor = executor
        self.session = session or SessionState()
        self._worker: CommandWorker | None = None
        self._pending_commands: deque[str] = deque()
        self._completion_engine = CompletionEngine(self.session, lambda: self._translator.available_commands(self.session))
        self._active_command: str | None = None
        self._capture_pager_output = False
        self._captured_stdout_parts: list[str] = []
        self._captured_stderr_parts: list[str] = []
        self._pager_command: str | None = None
        self._pager_lines: list[str] = []
        self._pager_index = 0
        self._pager_exit_code = 0
        self._pager_page_size = 24
        self._pager_prompt_text: str | None = None

        self.setObjectName("terminalPane")
        self.setFrameShape(QFrame.StyledPanel)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)        

        self.title_label = QLabel("terminal")
        self.status_label = QLabel("idle")
        self.terminal_view = TerminalView(self.session.history, completion_provider=self._complete_input)
        self.terminal_view.execute_requested.connect(self.run_current_command)  
        self.terminal_view.activated.connect(self._emit_activated)
        self.terminal_view.completion_candidates_requested.connect(self._show_completion_candidates)
        self.terminal_view.transcript.installEventFilter(self)

        self.clear_button = QPushButton("clear")
        self.clear_button.clicked.connect(self.clear_output)
        self.split_h_button = QPushButton("split-h")
        self.split_h_button.clicked.connect(lambda: self.split_requested.emit(self, Qt.Vertical))
        self.split_v_button = QPushButton("split-v")
        self.split_v_button.clicked.connect(lambda: self.split_requested.emit(self, Qt.Horizontal))
        self.close_button = QPushButton("x")
        self.close_button.clicked.connect(lambda: self.close_requested.emit(self))

        self._build_layout()
        self.update_prompt()
        self.append_info("PSux ready. Linux-style commands run as native Windows commands without WSL.")
        self.append_info("Ctrl+Enter run | Ctrl+L clear | Ctrl+Shift+H horizontal split | Ctrl+Shift+V vertical split | Ctrl+W close pane")
        self.focus_command_input()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(6)
        header.addWidget(self.title_label)
        header.addStretch(1)
        header.addWidget(self.status_label)
        header.addWidget(self.clear_button)
        header.addWidget(self.split_h_button)
        header.addWidget(self.split_v_button)
        header.addWidget(self.close_button)

        root.addLayout(header)
        root.addWidget(self.terminal_view, 1)

        self.setStyleSheet(
            """
            QFrame#terminalPane {
                background-color: #0f1117;
                border: 1px solid #242a34;
                border-radius: 10px;
            }
            QFrame#terminalPane[active="true"] {
                border: 1px solid #52a7ff;
            }
            QLabel {
                color: #8692a2;
                font-size: 11px;
            }
            QPushButton {
                background-color: #151922;
                color: #9aa6b2;
                border: 1px solid #232a35;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QPushButton:disabled {
                color: #596270;
            }
            QPushButton:hover {
                border-color: #4c87c8;
                color: #dce6f2;
            }
            """
        )

    def _emit_activated(self) -> None:
        if is_qobject_alive(self):
            self.activated.emit(self)

    def set_active(self, active: bool) -> None:
        if not is_qobject_alive(self):
            return
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def update_prompt(self) -> None:
        if not is_qobject_alive(self) or not is_qobject_alive(self.terminal_view):
            return
        prompt_parts = build_prompt_parts(self.session.cwd)
        self.terminal_view.set_prompt_parts(prompt_parts)
        if is_qobject_alive(self.terminal_view.prompt_label):
            self.terminal_view.prompt_label.setToolTip(str(self.session.cwd))   

    def clear_output(self) -> None:
        if not is_qobject_alive(self.terminal_view):
            return
        self.terminal_view.clear_transcript()
        self.update_prompt()

    def append_info(self, message: str) -> None:
        if is_qobject_alive(self.terminal_view) and is_qobject_alive(self.terminal_view.transcript):
            self.terminal_view.transcript.append_info(message)

    def append_error(self, message: str) -> None:
        if is_qobject_alive(self.terminal_view) and is_qobject_alive(self.terminal_view.transcript):
            self.terminal_view.transcript.append_error(message)

    def focus_command_input(self) -> None:
        if is_qobject_alive(self.terminal_view):
            self.terminal_view.focus_input()

    def set_command_text(self, command: str) -> None:
        if not is_qobject_alive(self.terminal_view) or not is_qobject_alive(self.terminal_view.input):
            return
        self.terminal_view.input.setText(command)
        self.terminal_view.input.setCursorPosition(len(command))
        self.focus_command_input()

    def execute_command_text(self, command: str) -> None:
        self.enqueue_commands([command], focus_when_done=True)

    def execute_command_lines(self, commands: list[str]) -> None:
        self.enqueue_commands(commands, focus_when_done=True)

    def enqueue_commands(self, commands: list[str], focus_when_done: bool = True) -> None:
        normalized = [command.strip() for command in commands if command.strip()]
        if not normalized:
            return
        for command in normalized:
            self._pending_commands.append(command)
        if len(normalized) > 1:
            self.append_info(f"Queued {len(normalized)} commands.")
        if focus_when_done:
            self.focus_command_input()
        self._start_next_command()

    def run_current_command(self) -> None:
        if not is_qobject_alive(self) or not is_qobject_alive(self.terminal_view):
            return
        self._emit_activated()

        command = self.terminal_view.current_command().strip()
        if not command:
            return

        self.terminal_view.clear_command()
        self.enqueue_commands([command], focus_when_done=False)

    def _execute_internal(self, plan) -> None:
        if not is_qobject_alive(self):
            return
        action = plan.internal_action
        if action == "clear":
            self.clear_output()
            return
        if action == "cd":
            try:
                self.session.change_directory(plan.payload.get("path"))
            except UserFacingError as exc:
                self.append_error(str(exc))
                return
            self.update_prompt()
            return
        if action == "export":
            self.session.set_env_var(plan.payload["name"], plan.payload["value"])
            self.append_info(f"export: set {plan.payload['name']} for this pane session.")
            return
        if action == "history":
            self.terminal_view.transcript.append_output(plan.payload.get("text", ""))
            return
        self.append_error(f"Unsupported internal action: {action}")

    def _run_external(self, plan) -> None:
        if not is_qobject_alive(self):
            return
        self._set_running_state(True)

        worker = CommandWorker(
            self._executor,
            plan,
            self.session.cwd,
            self.session.get_effective_env(),
        )
        worker.output_received.connect(self._handle_execution_output)
        worker.completed.connect(self._handle_execution_result)
        worker.finished.connect(worker.deleteLater)
        self._worker = worker
        worker.start()

    def _set_running_state(self, running: bool) -> None:
        self.session.busy = running
        if is_qobject_alive(self.status_label):
            self.status_label.setText("running" if running else "idle")
        if is_qobject_alive(self.terminal_view):
            cmd_text = self._active_command if running else None
            if running and getattr(self, '_pager_command', None):
                cmd_text = getattr(self, '_pager_prompt_text', None) or ("[pager] " + self._pager_command)
            self.terminal_view.set_busy(running, cmd_text)

    def _handle_execution_output(self, text: str, is_stderr: bool) -> None:     
        if not text or not is_qobject_alive(self) or not is_qobject_alive(self.terminal_view):
            return
        if self._capture_pager_output:
            if is_stderr:
                self._captured_stderr_parts.append(text)
            else:
                self._captured_stdout_parts.append(text)
            return
        if not is_qobject_alive(self.terminal_view.transcript):
            return
        if is_stderr:
            self.terminal_view.transcript.append_stream_error(text)
        else:
            self.terminal_view.transcript.append_stream_output(text)

    def _handle_execution_result(self, result: ExecutionResult) -> None:        
        if not is_qobject_alive(self):
            return

        capture_mode = self._capture_pager_output
        captured_stdout = "".join(self._captured_stdout_parts)
        captured_stderr = "".join(self._captured_stderr_parts)
        self._capture_pager_output = False
        self._captured_stdout_parts.clear()
        self._captured_stderr_parts.clear()

        pager_started = False
        if capture_mode:
            if captured_stderr and is_qobject_alive(self.terminal_view) and is_qobject_alive(self.terminal_view.transcript):
                self.terminal_view.transcript.append_stream_error(captured_stderr)
            if result.exit_code == 0 and captured_stdout:
                pager_started = True
                self._start_pager(self._active_command or "command", captured_stdout, result.exit_code)
            elif captured_stdout and is_qobject_alive(self.terminal_view) and is_qobject_alive(self.terminal_view.transcript):
                self.terminal_view.transcript.append_stream_output(captured_stdout)

        if result.exit_code != 0 and not result.stderr and is_qobject_alive(self.terminal_view) and is_qobject_alive(self.terminal_view.transcript):
            self.terminal_view.transcript.append_error(f"Command exited with code {result.exit_code}.")

        self._worker = None
        if not pager_started:
            self._finish_active_command(result.exit_code)

    def _complete_non_process_command(self) -> None:
        self._active_command = None
        self._worker = None
        if self._pending_commands:
            self._start_next_command()
            return
        if self.session.busy:
            self._set_running_state(False)
        self.update_prompt()
        self.focus_command_input()

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        self._emit_activated()

    def eventFilter(self, watched, event) -> bool:
        if (
            watched is getattr(self.terminal_view, "transcript", None)
            and self._pager_command is not None
            and event.type() == QEvent.KeyPress
        ):
            modifiers = event.modifiers()
            if not (modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)):
                key = event.key()
                if key in {Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space, Qt.Key_PageDown}:
                    self._show_next_pager_page()
                    return True
                if key in {Qt.Key_Q, Qt.Key_Escape}:
                    self._pager_prompt_text = None
                    self._close_pager()
                    return True
        return super().eventFilter(watched, event)

    def _complete_input(self, text: str, cursor_position: int, repeated: bool):
        return self._completion_engine.complete(text, cursor_position, repeated)
    def _show_completion_candidates(self, candidates: list[str]) -> None:       
        if not candidates:
            return
        width = max(len(candidate) for candidate in candidates) + 2
        columns = max(1, min(4, 80 // max(width, 1)))
        rows = []
        for index in range(0, len(candidates), columns):
            chunk = candidates[index : index + columns]
            rows.append("".join(candidate.ljust(width) for candidate in chunk).rstrip())
        self.append_info("\n".join(rows))

    def _start_next_command(self) -> None:
        if not is_qobject_alive(self) or self._worker is not None or not self._pending_commands:
            return

        command = self._pending_commands.popleft()
        self._active_command = command
        self._capture_pager_output = self._is_pager_command(command)
        self._captured_stdout_parts.clear()
        self._captured_stderr_parts.clear()
        if self.session.busy:
            self._set_running_state(True)
        self.session.history.add(command)
        prompt_parts = build_prompt_parts(self.session.cwd)
        if is_qobject_alive(self.terminal_view) and is_qobject_alive(self.terminal_view.transcript):
            self.terminal_view.transcript.append_command(prompt_parts, command) 

        try:
            plan = self._translator.translate(command, self.session)
        except UserFacingError as exc:
            self.append_error(str(exc))
            self._complete_non_process_command()
            return

        if plan is None:
            self._complete_non_process_command()
            return

        if plan.compatibility_note:
            self.append_info(plan.compatibility_note)

        if plan.kind == "internal":
            self._execute_internal(plan)
            self._complete_non_process_command()
            return

        self._run_external(plan)

    def _finish_active_command(self, exit_code: int) -> None:
        finished_command = self._active_command or "<unknown>"
        self.append_info(f"[{finished_command}] done (exit {exit_code})")       
        self._worker = None
        self._active_command = None
        if self._pending_commands:
            self._start_next_command()
            return
        self._set_running_state(False)
        self.update_prompt()
        self.focus_command_input()

    def _is_pager_command(self, command: str) -> bool:
        tokens = command.strip().split()
        if not tokens:
            return False
        if len(tokens) >= 2 and tokens[0].lower() == "git" and tokens[1].lower() in {"log", "diff", "show"}:
            return True
        if tokens[0].lower() in {"less", "more"}:
            return True
        return False

    def _start_pager(self, command: str, output: str, exit_code: int) -> None:
        lines = output.splitlines()
        if not lines:
            self._finish_active_command(exit_code)
            return
        self._pager_command = command
        self._pager_lines = lines
        self._pager_index = 0
        self._pager_exit_code = exit_code
        self._pager_prompt_text = None
        self._set_running_state(True)
        if is_qobject_alive(self.terminal_view) and is_qobject_alive(self.terminal_view.transcript):
            self.terminal_view.transcript.setFocus(Qt.OtherFocusReason)
        self._show_next_pager_page()

    def _show_next_pager_page(self) -> None:
        if self._pager_command is None:
            return
        start = self._pager_index
        end = min(start + self._pager_page_size, len(self._pager_lines))
        chunk = "\n".join(self._pager_lines[start:end])
        if chunk and is_qobject_alive(self.terminal_view) and is_qobject_alive(self.terminal_view.transcript):
            self.terminal_view.transcript.append_output(chunk)
            cursor = self.terminal_view.transcript.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.terminal_view.transcript.setTextCursor(cursor)
        self._pager_index = end
        if self._pager_index < len(self._pager_lines):
            remaining = len(self._pager_lines) - self._pager_index
            self._pager_prompt_text = f"--More-- ({remaining} lines remaining) [Enter/Space=next, q/Esc=quit]"
            self._set_running_state(True)
            return
        self._pager_prompt_text = None
        self._close_pager()

    def _close_pager(self) -> None:
        exit_code = self._pager_exit_code
        self._pager_command = None
        self._pager_lines = []
        self._pager_index = 0
        self._pager_exit_code = 0
        self._pager_prompt_text = None
        self._finish_active_command(exit_code)