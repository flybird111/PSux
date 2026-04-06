from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(slots=True)
class QuickCommand:
    id: str
    name: str
    category: str
    command: str
    note: str = ""

    def matches(self, query: str) -> bool:
        if not query:
            return True
        needle = query.lower()
        haystacks = (self.name, self.category, self.note)
        return any(needle in value.lower() for value in haystacks)

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "command": self.command,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> "QuickCommand":
        return cls(
            id=data.get("id") or uuid.uuid4().hex,
            name=data.get("name", "").strip(),
            category=data.get("category", "Custom").strip() or "Custom",
            command=data.get("command", "").strip(),
            note=data.get("note", "").strip(),
        )
