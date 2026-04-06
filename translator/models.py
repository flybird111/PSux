from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CommandPlan:
    kind: str
    display_command: str
    support_level: str = "fully_supported"
    powershell_script: str | None = None
    executable: str | None = None
    arguments: list[str] = field(default_factory=list)
    internal_action: str | None = None
    compatibility_note: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
