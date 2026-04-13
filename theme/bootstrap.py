import os
import sys
import types


def app_directory() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def startup_log_path() -> str:
    return os.path.join(app_directory(), "quick_command.startup.log")


def write_startup_log(message: str) -> None:
    try:
        with open(startup_log_path(), "a", encoding="utf-8") as file:
            file.write(message.rstrip() + "\n")
    except Exception:
        pass


write_startup_log("module import: stdlib ready")
darkdetect_stub = types.ModuleType("darkdetect")
darkdetect_stub.theme = lambda: "Dark"
darkdetect_stub.isDark = lambda: True
darkdetect_stub.isLight = lambda: False
darkdetect_stub.listener = lambda callback: None
sys.modules.setdefault("darkdetect", darkdetect_stub)
write_startup_log("module import: darkdetect stub installed")

import customtkinter as ctk

write_startup_log("module import: customtkinter ready")
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")
write_startup_log("module import: customtkinter theme configured")
