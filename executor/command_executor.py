from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QThread, Signal

from translator import CommandPlan
from utils.text import decode_output


@dataclass
class ExecutionResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0


StreamCallback = Callable[[str], None]


class CommandExecutor:
    def execute(
        self,
        plan: CommandPlan,
        cwd: Path,
        env: dict[str, str],
        stdout_callback: StreamCallback | None = None,
        stderr_callback: StreamCallback | None = None,
    ) -> ExecutionResult:
        if plan.kind not in {"powershell", "native", "batch", "detached_native"}:
            raise ValueError(f"Unsupported execution kind: {plan.kind}")

        if plan.kind == "detached_native":
            return self._run_detached_native(plan, cwd, env)

        process = self._spawn_process(plan, cwd, env)
        return self._collect_streaming_output(process, stdout_callback, stderr_callback)

    def _spawn_process(self, plan: CommandPlan, cwd: Path, env: dict[str, str]) -> subprocess.Popen[bytes]:
        if plan.kind == "powershell":
            script = (
                "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
                "$OutputEncoding = [System.Text.Encoding]::UTF8; "
                "$ErrorActionPreference = 'Stop'; "
                f"{plan.powershell_script}"
            )
            args = [
                "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ]
        elif plan.kind == "batch":
            args = ["cmd.exe", "/c", plan.executable or "", *plan.arguments]
        else:
            args = [plan.executable or "", *plan.arguments]

        return subprocess.Popen(
            args,
            cwd=str(cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    def _collect_streaming_output(
        self,
        process: subprocess.Popen[bytes],
        stdout_callback: StreamCallback | None,
        stderr_callback: StreamCallback | None,
    ) -> ExecutionResult:
        stdout_parts: list[str] = []
        stderr_parts: list[str] = []

        def pump(stream, parts: list[str], callback: StreamCallback | None) -> None:
            if stream is None:
                return
            try:
                for chunk in iter(stream.readline, b""):
                    if not chunk:
                        break
                    text = decode_output(chunk)
                    if not text:
                        continue
                    parts.append(text)
                    if callback is not None:
                        callback(text)
            finally:
                stream.close()

        stdout_thread = threading.Thread(
            target=pump,
            args=(process.stdout, stdout_parts, stdout_callback),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=pump,
            args=(process.stderr, stderr_parts, stderr_callback),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()
        exit_code = process.wait()
        stdout_thread.join()
        stderr_thread.join()

        return ExecutionResult(
            stdout="".join(stdout_parts),
            stderr="".join(stderr_parts),
            exit_code=exit_code,
        )

    def _run_detached_native(self, plan: CommandPlan, cwd: Path, env: dict[str, str]) -> ExecutionResult:
        subprocess.Popen(
            [plan.executable or "", *plan.arguments],
            cwd=str(cwd),
            env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return ExecutionResult()


class CommandWorker(QThread):
    output_received = Signal(str, bool)
    completed = Signal(object)

    def __init__(self, executor: CommandExecutor, plan: CommandPlan, cwd: Path, env: dict[str, str]) -> None:
        super().__init__()
        self._executor = executor
        self._plan = plan
        self._cwd = cwd
        self._env = env

    def run(self) -> None:
        try:
            result = self._executor.execute(
                self._plan,
                self._cwd,
                self._env,
                stdout_callback=lambda text: self.output_received.emit(text, False),
                stderr_callback=lambda text: self.output_received.emit(text, True),
            )
        except Exception as exc:  # noqa: BLE001
            result = ExecutionResult(stderr=str(exc), exit_code=1)
            self.output_received.emit(result.stderr, True)
        self.completed.emit(result)
