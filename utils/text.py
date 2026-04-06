from __future__ import annotations

import locale
import re


def decode_output(data: bytes | None) -> str:
    if not data:
        return ""

    encodings = ["utf-8", locale.getpreferredencoding(False), "gbk", "utf-16-le"]
    for encoding in encodings:
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def quote_powershell(value: str) -> str:
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


_ENV_TOKEN_PATTERN = re.compile(r"\$(\w+)|\$\{([^}]+)\}")


def expand_env_tokens(text: str, env: dict[str, str]) -> str:
    def replacer(match: re.Match[str]) -> str:
        name = match.group(1) or match.group(2) or ""
        return env.get(name, "")

    return _ENV_TOKEN_PATTERN.sub(replacer, text)
