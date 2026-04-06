from __future__ import annotations

import uuid

from quick_commands.models import QuickCommand
from quick_commands.storage import QuickCommandsStorage


DEFAULT_CATEGORY = "General"


class QuickCommandsManager:
    def __init__(self, storage: QuickCommandsStorage) -> None:
        self._storage = storage
        loaded = self._storage.load()
        self._commands = loaded["commands"]
        self._categories = loaded["categories"] or [DEFAULT_CATEGORY]
        self._normalize_categories()

    @property
    def commands(self) -> list[QuickCommand]:
        return list(self._commands)

    @property
    def categories(self) -> list[str]:
        return list(self._categories)

    def search(self, query: str, category: str = "All") -> list[QuickCommand]:
        filtered = [
            command
            for command in self._commands
            if command.matches(query) and (category == "All" or command.category == category)
        ]
        return sorted(filtered, key=lambda item: (item.category.lower(), item.name.lower()))

    def add_command(self, name: str, category: str, command: str, note: str = "") -> QuickCommand:
        normalized_category = self.ensure_category(category)
        quick_command = QuickCommand(
            id=uuid.uuid4().hex,
            name=name.strip(),
            category=normalized_category,
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
        existing.category = self.ensure_category(category)
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

    def ensure_category(self, category: str) -> str:
        normalized = category.strip() or DEFAULT_CATEGORY
        if normalized not in self._categories:
            self._categories.append(normalized)
            self._sort_categories()
        return normalized

    def rename_category(self, old_name: str, new_name: str) -> str:
        old_name = old_name.strip()
        new_name = new_name.strip() or DEFAULT_CATEGORY
        if old_name not in self._categories:
            raise ValueError("Category not found.")
        if old_name == new_name:
            return new_name
        if new_name in self._categories:
            raise ValueError("Category already exists.")

        index = self._categories.index(old_name)
        self._categories[index] = new_name
        for command in self._commands:
            if command.category == old_name:
                command.category = new_name
        self._sort_categories()
        self.save()
        return new_name

    def delete_category(self, name: str, fallback: str | None = None) -> str:
        name = name.strip()
        if name not in self._categories:
            raise ValueError("Category not found.")
        if len(self._categories) == 1:
            raise ValueError("At least one category must remain.")

        replacement = self.ensure_category((fallback or DEFAULT_CATEGORY).strip() or DEFAULT_CATEGORY)
        if replacement == name:
            alternatives = [category for category in self._categories if category != name]
            replacement = alternatives[0]

        self._categories = [category for category in self._categories if category != name]
        for command in self._commands:
            if command.category == name:
                command.category = replacement
        self._sort_categories()
        self.save()
        return replacement

    def save(self) -> None:
        self._normalize_categories()
        self._storage.save(self._commands, self._categories)

    def _normalize_categories(self) -> None:
        discovered = {command.category.strip() for command in self._commands if command.category.strip()}
        normalized = {category.strip() for category in self._categories if category.strip()}
        normalized.update(discovered)
        if not normalized:
            normalized = {DEFAULT_CATEGORY}
        self._categories = sorted(normalized, key=str.lower)
        for command in self._commands:
            if not command.category.strip():
                command.category = self._categories[0]

    def _sort_categories(self) -> None:
        self._categories = sorted(set(self._categories), key=str.lower)

    def _validate(self, command: QuickCommand) -> None:
        if not command.name:
            raise ValueError("Quick command name is required.")
        if not command.command:
            raise ValueError("Quick command content is required.")
