from __future__ import annotations

import uuid

from quick_commands.models import QuickCommand
from quick_commands.storage import QuickCommandsStorage


DEFAULT_CATEGORIES = [
    "Unreal Build",
    "Git",
    "PowerShell",
    "Python",
    "Custom",
]
class QuickCommandsManager:
    def __init__(self, storage: QuickCommandsStorage) -> None:
        self._storage = storage
        self._commands = self._storage.load()

    @property
    def commands(self) -> list[QuickCommand]:
        return list(self._commands)

    @property
    def categories(self) -> list[str]:
        discovered = {command.category for command in self._commands if command.category}
        return sorted(set(DEFAULT_CATEGORIES) | discovered, key=str.lower)

    def search(self, query: str) -> list[QuickCommand]:
        filtered = [command for command in self._commands if command.matches(query)]
        return sorted(filtered, key=lambda item: (item.category.lower(), item.name.lower()))

    def add_command(self, name: str, category: str, command: str, note: str = "") -> QuickCommand:
        quick_command = QuickCommand(
            id=uuid.uuid4().hex,
            name=name.strip(),
            category=category.strip() or "Custom",
            command=command.strip(),
            note=note.strip(),
        )
        self._validate(quick_command)
        self._commands.append(quick_command)
        self.save()
        return quick_command

    def update_command(self, command_id: str, name: str, category: str, command: str, note: str = "") -> QuickCommand:
        existing = self.get(command_id)
        if existing is None:
            raise ValueError("Quick command not found.")
        existing.name = name.strip()
        existing.category = category.strip() or "Custom"
        existing.command = command.strip()
        existing.note = note.strip()
        self._validate(existing)
        self.save()
        return existing

    def delete_command(self, command_id: str) -> None:
        self._commands = [command for command in self._commands if command.id != command_id]
        self.save()

    def get(self, command_id: str) -> QuickCommand | None:
        return next((command for command in self._commands if command.id == command_id), None)

    def save(self) -> None:
        self._storage.save(self._commands)

    def _validate(self, command: QuickCommand) -> None:
        if not command.name:
            raise ValueError("Quick command name is required.")
        if not command.command:
            raise ValueError("Quick command content is required.")
