import json
import os
import time
import uuid
from typing import Any, Dict, List


class DataStore:
    def __init__(self, file_path: str) -> None:
        self.file_path = file_path

    def _default_data(self) -> Dict[str, List[Dict[str, Any]]]:
        return {"groups": []}

    def _normalize(self, data: Any) -> Dict[str, List[Dict[str, Any]]]:
        if not isinstance(data, dict):
            return self._default_data()
        groups = data.get("groups", [])
        if not isinstance(groups, list):
            groups = []
        normalized_groups: List[Dict[str, Any]] = []
        for group in groups:
            if not isinstance(group, dict):
                continue
            items = group.get("items", [])
            if not isinstance(items, list):
                items = []
            normalized_items: List[Dict[str, Any]] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                commands = item.get("commands", [])
                if not isinstance(commands, list):
                    commands = []
                normalized_commands: List[Dict[str, str]] = []
                for command in commands:
                    if isinstance(command, dict):
                        command_text = str(command.get("command", "")).strip()
                        command_id = str(command.get("id", "")) or uuid.uuid4().hex
                    else:
                        command_text = str(command).strip()
                        command_id = uuid.uuid4().hex
                    if command_text:
                        normalized_commands.append({"id": command_id, "command": command_text})
                normalized_items.append({
                    "id": str(item.get("id", "")) or uuid.uuid4().hex,
                    "name": str(item.get("name", "New Item")).strip() or "New Item",
                    "commands": normalized_commands,
                })
            normalized_groups.append({
                "id": str(group.get("id", "")) or uuid.uuid4().hex,
                "name": str(group.get("name", "New Group")).strip() or "New Group",
                "items": normalized_items,
            })
        return {"groups": normalized_groups}

    def load(self) -> Dict[str, List[Dict[str, Any]]]:
        if not os.path.exists(self.file_path):
            data = self._default_data()
            self.save(data)
            return data
        try:
            with open(self.file_path, "r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError):
            data = self._default_data()
            self.save(data)
            return data
        normalized = self._normalize(data)
        self.save(normalized)
        return normalized

    def save(self, data: Dict[str, List[Dict[str, Any]]]) -> None:
        directory = os.path.dirname(self.file_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        temp_path = f"{self.file_path}.tmp"
        with open(temp_path, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
        for _ in range(5):
            try:
                os.replace(temp_path, self.file_path)
                return
            except PermissionError:
                time.sleep(0.1)
        try:
            with open(self.file_path, "w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
        finally:
            try:
                os.remove(temp_path)
            except OSError:
                pass
