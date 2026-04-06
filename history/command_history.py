from __future__ import annotations


class CommandHistory:
    def __init__(self) -> None:
        self._items: list[str] = []
        self._cursor: int | None = None
        self._draft: str = ""

    @property
    def items(self) -> list[str]:
        return list(self._items)

    def add(self, command: str) -> None:
        cleaned = command.strip()
        if not cleaned:
            return
        if not self._items or self._items[-1] != cleaned:
            self._items.append(cleaned)
        self.reset_navigation()

    def previous(self, current_text: str) -> str:
        if not self._items:
            return current_text
        if self._cursor is None:
            self._draft = current_text
            self._cursor = len(self._items)
        if self._cursor > 0:
            self._cursor -= 1
        return self._items[self._cursor]

    def next(self) -> str:
        if self._cursor is None:
            return self._draft
        if self._cursor < len(self._items) - 1:
            self._cursor += 1
            return self._items[self._cursor]
        self._cursor = None
        return self._draft

    def reset_navigation(self) -> None:
        self._cursor = None
        self._draft = ""
