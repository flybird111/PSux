from __future__ import annotations

import json
import os
from pathlib import Path

from quick_commands.models import QuickCommand


class QuickCommandsStorage:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or self._default_path()

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> list[QuickCommand]:
        if not self._path.exists():
            return []

        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

        raw_commands = data.get("commands", [])
        return [QuickCommand.from_dict(item) for item in raw_commands if isinstance(item, dict)]

    def save(self, commands: list[QuickCommand]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "commands": [command.to_dict() for command in commands],
        }
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _default_path(self) -> Path:
        appdata = os.getenv("APPDATA")
        if appdata:
            return Path(appdata) / "PSux" / "quick_commands.json"
        return Path.home() / ".psux" / "quick_commands.json"
