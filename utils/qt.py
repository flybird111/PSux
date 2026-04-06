from __future__ import annotations

from typing import Any

from shiboken6 import isValid


def is_qobject_alive(obj: Any) -> bool:
    """Qt can delete the C++ object while the Python wrapper still exists."""
    return obj is not None and isValid(obj)
