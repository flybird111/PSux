from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from session import SessionState
from utils.path_utils import resolve_user_path


@dataclass
class CompletionOutcome:
    text: str
    cursor_position: int
    candidates: list[str]
    displayed: bool = False


@dataclass
class _ParsedLine:
    tokens: list[str]
    active_fragment: str
    active_start: int
    quote_char: str | None


_ALWAYS_PATH_COMMANDS = {
    "basename",
    "cat",
    "cd",
    "dirname",
    "head",
    "less",
    "open",
    "realpath",
    "rm",
    "sort",
    "tail",
    "touch",
    "tree",
    "uniq",
    "vim",
    "wc",
}


class CompletionEngine:
    def __init__(self, session: SessionState, commands: Iterable[str] | Callable[[], Iterable[str]]) -> None:
        self._session = session
        self._commands = commands

    def complete(self, text: str, cursor_position: int, repeated: bool = False) -> CompletionOutcome | None:
        prefix = text[:cursor_position]
        suffix = text[cursor_position:]
        parsed = self._parse_line(prefix)
        index = len(parsed.tokens)

        command = parsed.tokens[0] if parsed.tokens else None
        if index == 0 and not parsed.active_fragment.startswith("./"):
            candidates = self._command_candidates(parsed.active_fragment)
            return self._build_outcome(text, suffix, parsed, candidates, repeated, append_space=True, directory_mode=False)

        if index == 0 and parsed.active_fragment.startswith("./"):
            candidates = self._path_candidates(parsed.active_fragment, directories_only=False)
            return self._build_outcome(text, suffix, parsed, candidates, repeated, append_space=True, directory_mode=False)

        if not command:
            return None

        directories_only = self._directories_only_for(command, parsed.tokens)
        if not self._should_complete_path(command, parsed.tokens, parsed.active_fragment):
            return None

        candidates = self._path_candidates(parsed.active_fragment, directories_only=directories_only)
        append_space = not directories_only
        return self._build_outcome(text, suffix, parsed, candidates, repeated, append_space=append_space, directory_mode=directories_only)

    def _build_outcome(
        self,
        original_text: str,
        suffix: str,
        parsed: _ParsedLine,
        candidates: list[str],
        repeated: bool,
        append_space: bool,
        directory_mode: bool,
    ) -> CompletionOutcome | None:
        if not candidates:
            return None

        if len(candidates) == 1:
            replacement = self._format_unique_candidate(
                candidates[0],
                parsed,
                append_space=append_space,
                directory_mode=directory_mode,
            )
            new_text = original_text[: parsed.active_start] + replacement + suffix
            new_cursor = parsed.active_start + len(replacement)
            return CompletionOutcome(new_text, new_cursor, candidates)

        common_prefix = self._common_prefix(candidates)
        if len(common_prefix) > len(parsed.active_fragment):
            replacement = self._format_token(common_prefix, parsed.quote_char, final=False, append_space=False)
            new_text = original_text[: parsed.active_start] + replacement + suffix
            new_cursor = parsed.active_start + len(replacement)
            return CompletionOutcome(new_text, new_cursor, candidates)

        return CompletionOutcome(original_text, parsed.active_start + len(self._format_token(parsed.active_fragment, parsed.quote_char, final=False, append_space=False)), candidates, displayed=repeated)

    def _format_unique_candidate(
        self,
        candidate: str,
        parsed: _ParsedLine,
        append_space: bool,
        directory_mode: bool,
    ) -> str:
        is_directory = self._candidate_is_directory(candidate)

        # For directory-oriented commands like `cd`, completing to `history/`
        # is more helpful than `history` because it immediately shows that the
        # target is a directory and allows continuing deeper on the next Tab.
        if directory_mode and is_directory:
            candidate = self._with_directory_suffix(candidate, parsed.active_fragment)
            return self._format_token(candidate, parsed.quote_char, final=False, append_space=False)

        return self._format_token(candidate, parsed.quote_char, final=True, append_space=append_space)

    def _command_candidates(self, fragment: str) -> list[str]:
        commands = self._available_commands()
        if not fragment:
            return commands
        exact_matches = [command for command in commands if command.startswith(fragment)]
        if exact_matches:
            return exact_matches
        needle = fragment.lower()
        return [command for command in commands if command.lower().startswith(needle)]

    def _available_commands(self) -> list[str]:
        source = self._commands() if callable(self._commands) else self._commands
        return sorted(set(source), key=str.lower)

    def _path_candidates(self, fragment: str, directories_only: bool) -> list[str]:
        parent_fragment, name_prefix = self._split_fragment(fragment)
        try:
            base_dir = resolve_user_path(parent_fragment or ".", self._session.cwd)
        except OSError:
            return []

        try:
            entries = list(Path(base_dir).iterdir())
        except OSError:
            return []

        matches: list[tuple[str, bool]] = []
        fallback_matches: list[tuple[str, bool]] = []
        prefer_exact_case = any(char.isupper() for char in name_prefix)
        for entry in entries:
            if directories_only and not entry.is_dir():
                continue
            completion = f"{parent_fragment}{entry.name}"
            item = (completion, entry.is_dir())
            if prefer_exact_case and entry.name.startswith(name_prefix):
                matches.append(item)
                continue
            if entry.name.lower().startswith(name_prefix.lower()):
                fallback_matches.append(item)

        if not prefer_exact_case or not matches:
            matches = fallback_matches
        matches.sort(key=lambda item: (not item[1], item[0].lower()))
        return [item[0] for item in matches]

    def _candidate_is_directory(self, candidate: str) -> bool:
        try:
            return resolve_user_path(candidate, self._session.cwd).is_dir()
        except OSError:
            return False

    def _with_directory_suffix(self, candidate: str, original_fragment: str) -> str:
        if candidate.endswith(("/", "\\")):
            return candidate
        separator = "\\" if "\\" in original_fragment else "/"
        return f"{candidate}{separator}"

    def _split_fragment(self, fragment: str) -> tuple[str, str]:
        last_slash = max(fragment.rfind("/"), fragment.rfind("\\"))
        if last_slash == -1:
            return "", fragment
        return fragment[: last_slash + 1], fragment[last_slash + 1 :]

    def _parse_line(self, text: str) -> _ParsedLine:
        tokens: list[str] = []
        token_chars: list[str] = []
        token_start: int | None = None
        token_quote: str | None = None
        active_quote: str | None = None

        for index, char in enumerate(text):
            if active_quote:
                if char == active_quote:
                    active_quote = None
                else:
                    token_chars.append(char)
                continue

            if char in {"'", '"'}:
                if token_start is None:
                    token_start = index
                    token_quote = char
                active_quote = char
                continue

            if char.isspace():
                if token_start is not None:
                    tokens.append("".join(token_chars))
                    token_chars = []
                    token_start = None
                    token_quote = None
                continue

            if token_start is None:
                token_start = index
                token_quote = None
            token_chars.append(char)

        if token_start is None:
            return _ParsedLine(tokens=tokens, active_fragment="", active_start=len(text), quote_char=None)

        return _ParsedLine(tokens=tokens, active_fragment="".join(token_chars), active_start=token_start, quote_char=token_quote)

    def _format_token(self, value: str, quote_char: str | None, final: bool, append_space: bool) -> str:
        if quote_char:
            if final:
                return f"{quote_char}{value}{quote_char}" + (" " if append_space else "")
            return f"{quote_char}{value}"

        if any(char.isspace() for char in value):
            if final:
                return f"\"{value}\"" + (" " if append_space else "")
            return f"\"{value}"

        return value + (" " if final and append_space else "")

    def _common_prefix(self, values: list[str]) -> str:
        if not values:
            return ""
        prefix = values[0]
        for value in values[1:]:
            while not value.lower().startswith(prefix.lower()) and prefix:
                prefix = prefix[:-1]
        return prefix

    def _directories_only_for(self, command: str, preceding_tokens: list[str]) -> bool:
        return command == "cd"

    def _should_complete_path(self, command: str, preceding_tokens: list[str], active_fragment: str) -> bool:
        arg_count = len(preceding_tokens) - 1
        if command in _ALWAYS_PATH_COMMANDS:
            return True
        if command in {"cp", "mv"}:
            return arg_count <= 2
        if command == "ln":
            return arg_count <= 3
        if command == "grep":
            non_flags = [token for token in preceding_tokens[1:] if not token.startswith("-")]
            return len(non_flags) >= 1
        if command == "find":
            return not any(token in {"-name", "-iname"} for token in preceding_tokens[1:])
        if command.startswith("./"):
            return True
        if command in {"clear", "echo", "env", "export", "history", "kill", "ps", "which"}:
            return False
        if active_fragment.startswith("-"):
            return False
        return True
