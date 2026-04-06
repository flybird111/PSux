from __future__ import annotations

import os
from pathlib import Path


def resolve_user_path(raw_path: str, cwd: Path) -> Path:
    expanded = os.path.expanduser(raw_path.strip() or ".")
    candidate = Path(expanded)
    if not candidate.is_absolute():
        candidate = cwd / candidate
    return Path(os.path.abspath(str(candidate)))


def to_unix_display_path(path: Path) -> str:
    raw = os.path.abspath(str(path))
    home = os.path.abspath(os.path.expanduser("~"))

    if raw.lower().startswith(home.lower()):
        suffix = raw[len(home):].replace("\\", "/").strip("/")
        return "~" if not suffix else f"~/{suffix}"

    drive, tail = os.path.splitdrive(raw)
    normalized_tail = tail.replace("\\", "/").lstrip("/")
    if drive:
        drive_letter = drive.rstrip(":").lower()
        return f"/{drive_letter}" if not normalized_tail else f"/{drive_letter}/{normalized_tail}"
    return raw.replace("\\", "/")


def build_prompt_text(path: Path, app_name: str = "PSux") -> str:
    return f"{app_name}:{to_unix_display_path(path)}$"


def build_prompt_parts(path: Path, app_name: str = "PSux") -> tuple[str, str, str]:
    return app_name, to_unix_display_path(path), "$"
