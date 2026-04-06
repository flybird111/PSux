from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from translator import CommandPlan
from utils.text import decode_output


@dataclass
class ExecutionResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0


class CommandExecutor:
    def execute(self, plan: CommandPlan, cwd: Path, env: dict[str, str]) -> ExecutionResult:
        if plan.kind not in {"powershell", "native", "batch", "detached_native"}:
            raise ValueError(f"Unsupported execution kind: {plan.kind}")

        if plan.kind == "powershell":
            process = self._run_powershell(plan, cwd, env)
        elif plan.kind == "batch":
            process = self._run_batch(plan, cwd, env)
        elif plan.kind == "detached_native":
            return self._run_detached_native(plan, cwd, env)
        else:
            process = self._run_native(plan, cwd, env)

        return ExecutionResult(
            stdout=decode_output(process.stdout),
            stderr=decode_output(process.stderr),
            exit_code=process.returncode,
        )

    def _run_powershell(self, plan: CommandPlan, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[bytes]:
        script = (
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
            "$OutputEncoding = [System.Text.Encoding]::UTF8; "
            "$ErrorActionPreference = 'Stop'; "
            f"{plan.powershell_script}"
        )
        return subprocess.run(
            [
                "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            cwd=str(cwd),
            env=env,
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    def _run_native(self, plan: CommandPlan, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [plan.executable or "", *plan.arguments],
            cwd=str(cwd),
            env=env,
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    def _run_batch(self, plan: CommandPlan, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            ["cmd.exe", "/c", plan.executable or "", *plan.arguments],
            cwd=str(cwd),
            env=env,
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
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
    completed = Signal(object)

    def __init__(self, executor: CommandExecutor, plan: CommandPlan, cwd: Path, env: dict[str, str]) -> None:
        super().__init__()
        self._executor = executor
        self._plan = plan
        self._cwd = cwd
        self._env = env

    def run(self) -> None:
        try:
            result = self._executor.execute(self._plan, self._cwd, self._env)
        except Exception as exc:  # noqa: BLE001
            result = ExecutionResult(stderr=str(exc), exit_code=1)
        self.completed.emit(result)
