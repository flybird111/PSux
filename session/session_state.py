from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from history import CommandHistory
from utils.errors import UserFacingError
from utils.path_utils import resolve_user_path


@dataclass
class SessionState:
    cwd: Path = field(default_factory=lambda: Path.cwd())
    env: dict[str, str] = field(default_factory=dict)
    history: CommandHistory = field(default_factory=CommandHistory)
    busy: bool = False

    def __post_init__(self) -> None:
        self.cwd = Path(os.path.abspath(str(self.cwd)))

    def get_effective_env(self) -> dict[str, str]:
        merged = os.environ.copy()
        merged.update(self.env)
        return merged

    def resolve_path(self, raw_path: str | None) -> Path:
        return resolve_user_path(raw_path or ".", self.cwd)

    def change_directory(self, raw_path: str | None) -> Path:
        target = self.resolve_path(raw_path or "~")
        if not target.exists():
            raise UserFacingError(f"cd: no such file or directory: {raw_path}")
        if not target.is_dir():
            raise UserFacingError(f"cd: not a directory: {raw_path}")
        self.cwd = target
        return self.cwd

    def set_env_var(self, name: str, value: str) -> None:
        self.env[name] = value
