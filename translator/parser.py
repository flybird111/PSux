from __future__ import annotations

import shlex

from utils.errors import UserFacingError


class CommandParser:
    def parse(self, command_line: str) -> list[str]:
        try:
            tokens = shlex.split(command_line, posix=True)
        except ValueError as exc:
            raise UserFacingError(f"Unable to parse command: {exc}") from exc
        return tokens
