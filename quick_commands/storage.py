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

    def load(self) -> dict[str, list]:
        if not self._path.exists():
            return {"commands": [], "categories": []}

        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"commands": [], "categories": []}

        raw_commands = data.get("commands", [])
        raw_categories = data.get("categories", [])
        commands = [QuickCommand.from_dict(item) for item in raw_commands if isinstance(item, dict)]
        categories = [item.strip() for item in raw_categories if isinstance(item, str) and item.strip()]
        return {"commands": commands, "categories": categories}

    def save(self, commands: list[QuickCommand], categories: list[str]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 2,
            "categories": categories,
            "commands": [command.to_dict() for command in commands],
        }
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _default_path(self) -> Path:
        appdata = os.getenv("APPDATA")
        if appdata:
            return Path(appdata) / "PSux" / "quick_commands.json"
        return Path.home() / ".psux" / "quick_commands.json"
