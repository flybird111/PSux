import json
import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
import time
import traceback
import types
import uuid
from tkinter import messagebox, ttk
from typing import Any, Dict, List, Optional, Tuple


def app_directory() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def startup_log_path() -> str:
    return os.path.join(app_directory(), "quick_command.startup.log")


def write_startup_log(message: str) -> None:
    try:
        with open(startup_log_path(), "a", encoding="utf-8") as file:
            file.write(message.rstrip() + "\n")
    except Exception:
        pass


write_startup_log("module import: stdlib ready")

# Work around darkdetect blocking on Windows WMI queries during customtkinter import.
darkdetect_stub = types.ModuleType("darkdetect")
darkdetect_stub.theme = lambda: "Dark"
darkdetect_stub.isDark = lambda: True
darkdetect_stub.isLight = lambda: False
darkdetect_stub.listener = lambda callback: None
sys.modules.setdefault("darkdetect", darkdetect_stub)
write_startup_log("module import: darkdetect stub installed")

import customtkinter as ctk
write_startup_log("module import: customtkinter ready")
import pyte
write_startup_log("module import: pyte ready")
from pyte.screens import wcwidth
from winpty import PtyProcess
write_startup_log("module import: winpty ready")


ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")
write_startup_log("module import: customtkinter theme configured")


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

                normalized_items.append(
                    {
                        "id": str(item.get("id", "")) or uuid.uuid4().hex,
                        "name": str(item.get("name", "New Item")).strip() or "New Item",
                        "commands": normalized_commands,
                    }
                )

            normalized_groups.append(
                {
                    "id": str(group.get("id", "")) or uuid.uuid4().hex,
                    "name": str(group.get("name", "New Group")).strip() or "New Group",
                    "items": normalized_items,
                }
            )

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


class SingleLineDialog(ctk.CTkToplevel):
    def __init__(self, master: ctk.CTk, title: str, label: str, initial_value: str = "") -> None:
        super().__init__(master)
        self.result: Optional[str] = None

        self.title(title)
        self.geometry("420x180")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        container = ctk.CTkFrame(self, corner_radius=12)
        container.grid(row=0, column=0, padx=16, pady=16, sticky="nsew")
        container.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(container, text=label, anchor="w").grid(row=0, column=0, padx=16, pady=(16, 8), sticky="ew")

        self.entry = ctk.CTkEntry(container)
        self.entry.grid(row=1, column=0, padx=16, pady=(0, 12), sticky="ew")
        self.entry.insert(0, initial_value)

        button_frame = ctk.CTkFrame(container, fg_color="transparent")
        button_frame.grid(row=2, column=0, padx=16, pady=(0, 16), sticky="e")

        ctk.CTkButton(button_frame, text="Cancel", width=90, command=self.on_cancel).pack(side="right", padx=(8, 0))
        ctk.CTkButton(button_frame, text="OK", width=90, command=self.on_ok).pack(side="right")

        self.entry.bind("<Return>", lambda _event: self.on_ok())
        self.entry.bind("<Escape>", lambda _event: self.on_cancel())
        self.after(50, self._focus_input)

    def _focus_input(self) -> None:
        self.entry.focus_set()
        self.entry.select_range(0, "end")

    def on_ok(self) -> None:
        value = self.entry.get().strip()
        if not value:
            messagebox.showwarning("Warning", "Value cannot be empty.", parent=self)
            return
        self.result = value
        self.destroy()

    def on_cancel(self) -> None:
        self.result = None
        self.destroy()

    @classmethod
    def ask(cls, master: ctk.CTk, title: str, label: str, initial_value: str = "") -> Optional[str]:
        dialog = cls(master, title, label, initial_value)
        dialog.wait_window()
        return dialog.result


class CommandDialog(ctk.CTkToplevel):
    def __init__(self, master: ctk.CTk, title: str, initial_value: str = "") -> None:
        super().__init__(master)
        self.result: Optional[str] = None

        self.title(title)
        self.geometry("780x520")
        self.minsize(640, 380)
        self.transient(master)
        self.grab_set()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        container = ctk.CTkFrame(self, corner_radius=12)
        container.grid(row=0, column=0, padx=16, pady=16, sticky="nsew")
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            container,
            text="PowerShell Command",
            font=ctk.CTkFont(size=15, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, padx=16, pady=(16, 8), sticky="ew")

        self.textbox = ctk.CTkTextbox(container, wrap="word")
        self.textbox.grid(row=1, column=0, padx=16, pady=(0, 12), sticky="nsew")
        if initial_value:
            self.textbox.insert("1.0", initial_value)

        ctk.CTkLabel(
            container,
            text="Single-line and multi-line PowerShell scripts are both supported.",
            anchor="w",
            text_color=("gray35", "gray70"),
        ).grid(row=2, column=0, padx=16, pady=(0, 12), sticky="ew")

        button_frame = ctk.CTkFrame(container, fg_color="transparent")
        button_frame.grid(row=3, column=0, padx=16, pady=(0, 16), sticky="e")

        ctk.CTkButton(button_frame, text="Cancel", width=90, command=self.on_cancel).pack(side="right", padx=(8, 0))
        ctk.CTkButton(button_frame, text="Save", width=90, command=self.on_ok).pack(side="right")

        self.bind("<Escape>", lambda _event: self.on_cancel())
        self.after(50, self._focus_textbox)

    def _focus_textbox(self) -> None:
        self.textbox.focus_set()

    def on_ok(self) -> None:
        value = self.textbox.get("1.0", "end").strip()
        if not value:
            messagebox.showwarning("Warning", "Command content cannot be empty.", parent=self)
            return
        self.result = value
        self.destroy()

    def on_cancel(self) -> None:
        self.result = None
        self.destroy()

    @classmethod
    def ask(cls, master: ctk.CTk, title: str, initial_value: str = "") -> Optional[str]:
        dialog = cls(master, title, initial_value)
        dialog.wait_window()
        return dialog.result


class EmbeddedTerminal(ctk.CTkFrame):
    def __init__(self, master: ctk.CTkFrame, on_activate, initial_cwd: Optional[str] = None) -> None:
        super().__init__(master, corner_radius=10, fg_color=("#f4f6f8", "#11161e"))
        self.on_activate = on_activate
        self.pty_process: Optional[PtyProcess] = None
        self.output_queue: "queue.Queue[str]" = queue.Queue()
        self.reader_thread: Optional[threading.Thread] = None
        self.after_id: Optional[str] = None
        self.interrupt_after_id: Optional[str] = None
        self.resize_after_id: Optional[str] = None
        self.connected = False
        self.current_input = ""
        self.current_directory = initial_cwd or os.getcwd()
        self.previous_directory: Optional[str] = None
        self.prompt_pattern = re.compile(r"PS\s+(.+?)>\s*$")
        self.tail_buffer = ""
        self.is_command_line_mode = True
        self.columns = 120
        self.rows = 30
        self.font = tkfont.Font(family="Consolas", size=11)
        self.char_width = max(self.font.measure("M"), 1)
        self.line_height = max(self.font.metrics("linespace"), 1)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.text_widget = tk.Text(
            self,
            wrap="none",
            undo=False,
            font=self.font,
            bg="#0b1220",
            fg="#e5eefb",
            insertbackground="#e5eefb",
            relief="flat",
            bd=0,
            padx=10,
            pady=10,
            spacing1=0,
            spacing2=0,
            spacing3=0,
            insertwidth=2,
            takefocus=True,
        )
        self.text_widget.grid(row=0, column=0, sticky="nsew")

        self.y_scroll = ctk.CTkScrollbar(self, orientation="vertical", command=self.text_widget.yview)
        self.y_scroll.grid(row=0, column=1, sticky="ns")

        self.x_scroll = ctk.CTkScrollbar(self, orientation="horizontal", command=self.text_widget.xview)
        self.x_scroll.grid(row=1, column=0, sticky="ew")

        self.text_widget.configure(yscrollcommand=self.y_scroll.set, xscrollcommand=self.x_scroll.set)

        self.text_widget.bind("<Button-1>", self.on_click)
        self.text_widget.bind("<FocusIn>", self.on_focus)
        self.text_widget.bind("<Configure>", self.on_resize)
        self.text_widget.bind("<KeyPress>", self.on_key_press)
        self.text_widget.bind("<Control-v>", self.on_paste)
        self.text_widget.bind("<Control-V>", self.on_paste)
        self.text_widget.bind("<Control-c>", self.on_ctrl_c)
        self.text_widget.bind("<Control-C>", self.on_ctrl_c)
        self.text_widget.bind("<Button-3>", self.show_context_menu)

        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="Copy", command=self.copy_selection)
        self.context_menu.add_command(label="Paste", command=lambda: self.on_paste(None))
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Interrupt", command=lambda: self.on_ctrl_c(None))

        self.reset_screen()
        self.start_shell()
        self.schedule_output_pump()

    def resolve_shell_path(self) -> str:
        candidates = [
            os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "PowerShell", "7", "pwsh.exe"),
            os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe"),
            "powershell.exe",
        ]
        for candidate in candidates:
            if os.path.isabs(candidate):
                if os.path.exists(candidate):
                    return candidate
            else:
                return candidate
        return "powershell.exe"

    def shell_bootstrap_command(self) -> str:
        return (
            "$env:PAGER = ''; "
            "$env:GIT_PAGER = ''; "
            "$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); "
            "$ProgressPreference = 'SilentlyContinue'; "
            "try { Import-Module PSReadLine -ErrorAction Stop | Out-Null; "
            "Set-PSReadLineKeyHandler -Key Tab -Function Complete } catch { }"
        )

    def build_shell_args(self) -> List[str]:
        shell_path = self.resolve_shell_path()
        argv = [shell_path, "-NoLogo", "-NoProfile"]
        if os.path.basename(shell_path).lower() == "powershell.exe":
            argv.extend(["-ExecutionPolicy", "Bypass"])
        argv.extend(["-NoExit", "-Command", self.shell_bootstrap_command()])
        return argv

    def build_shell_env(self) -> Dict[str, str]:
        env = os.environ.copy()
        env.setdefault("TERM", "xterm-256color")
        env.setdefault("COLORTERM", "truecolor")
        env["PAGER"] = ""
        env["GIT_PAGER"] = ""
        return env

    def reset_screen(self) -> None:
        self.screen = pyte.HistoryScreen(self.columns, self.rows, 4000)
        self.stream = pyte.Stream(self.screen)
        self.render_screen()

    def start_shell(self) -> None:
        self.stop_shell()
        self.reset_screen()
        self.current_input = ""
        self.is_command_line_mode = True
        self.pty_process = PtyProcess.spawn(
            self.build_shell_args(),
            cwd=self.current_directory,
            env=self.build_shell_env(),
            dimensions=(self.rows, self.columns),
        )
        self.connected = True
        self.reader_thread = threading.Thread(target=self.reader_loop, daemon=True)
        self.reader_thread.start()

    def stop_shell(self) -> None:
        if self.pty_process is not None:
            try:
                self.pty_process.close()
            except Exception:
                pass
        self.pty_process = None
        self.connected = False

    def restart_shell(self) -> None:
        self.start_shell()

    def reader_loop(self) -> None:
        while self.pty_process is not None:
            try:
                chunk = self.pty_process.read(4096)
            except EOFError:
                break
            except Exception:
                break

            if chunk:
                self.output_queue.put(chunk)

        self.connected = False
        self.output_queue.put("\n[terminal disconnected]\n")

    def schedule_output_pump(self) -> None:
        self.process_output_queue()
        self.after_id = self.after(30, self.schedule_output_pump)

    def process_output_queue(self) -> None:
        chunks: List[str] = []
        while True:
            try:
                chunk = self.output_queue.get_nowait()
            except queue.Empty:
                break
            chunks.append(chunk)
        if chunks:
            self.stream.feed("".join(chunks))
            self.render_screen()

    def write_text(self, text: str) -> None:
        if self.pty_process is None:
            return
        try:
            self.pty_process.write(text)
        except Exception:
            self.connected = False

    def complete_input(self, current_input: str) -> str:
        if not current_input.strip():
            return current_input

        shell_path = self.resolve_shell_path()
        escaped_cwd = self.current_directory.replace("'", "''")
        script = (
            f"$cwd = '{escaped_cwd}'; "
            "if (Test-Path -LiteralPath $cwd) { Set-Location -LiteralPath $cwd }; "
            "$line = @'\n"
            f"{current_input}\n"
            "'@.TrimEnd(\"`r\", \"`n\"); "
            "$result = TabExpansion2 -inputScript $line -cursorColumn $line.Length; "
            "$matches = @($result.CompletionMatches | ForEach-Object { $_.CompletionText }); "
            "if (-not $matches -or $matches.Count -eq 0) { return }; "
            "if ($matches.Count -eq 1) { $matches[0]; return }; "
            "$prefix = $matches[0]; "
            "foreach ($match in $matches) { "
            "while (-not $match.StartsWith($prefix)) { "
            "$prefix = $prefix.Substring(0, $prefix.Length - 1); "
            "if ($prefix.Length -eq 0) { break } "
            "} "
            "} "
            "if ($prefix.Length -gt $line.Length) { $prefix } else { $matches[0] }"
        )
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        startup_info = None
        if os.name == "nt":
            startup_info = subprocess.STARTUPINFO()
            startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup_info.wShowWindow = 0

        try:
            result = subprocess.run(
                [shell_path, "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=3,
                creationflags=creation_flags,
                startupinfo=startup_info,
            )
        except Exception:
            return current_input

        completed = result.stdout.strip()
        if not completed:
            return current_input
        return self.normalize_completion(current_input, completed)

    def normalize_completion(self, original_input: str, completed_input: str) -> str:
        command_match = re.match(r"^(\s*)(cd|chdir|sl|Set-Location)(\s+)(.+)$", original_input, re.IGNORECASE)
        if not command_match:
            return completed_input

        leading, command_name, spacing, _path = command_match.groups()
        normalized_completed = completed_input
        if normalized_completed.startswith(".\\"):
            normalized_completed = normalized_completed[2:]
        elif normalized_completed.startswith("./"):
            normalized_completed = normalized_completed[2:]

        return f"{leading}{command_name}{spacing}{normalized_completed}"

    def sync_current_input(self, new_input: str) -> None:
        self.erase_current_input_from_terminal()
        if new_input:
            self.write_text(new_input)
        self.current_input = new_input

    def erase_current_input_from_terminal(self) -> None:
        if not self.current_input:
            return
        self.write_text("\x08" * len(self.current_input))
        self.write_text(" " * len(self.current_input))
        self.write_text("\x08" * len(self.current_input))

    def send_command(self, command_text: str) -> None:
        normalized = command_text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
        if not normalized:
            return

        payload = self.transform_command(normalized).replace("\n", "\r") + "\r"
        self.current_input = ""
        self.is_command_line_mode = False
        self.write_text(payload)
        self.text_widget.focus_set()

    def set_active(self, active: bool) -> None:
        border = "#3b82f6" if active else ("#b9c1c9" if ctk.get_appearance_mode() == "Light" else "#2a3240")
        self.configure(border_width=2, border_color=border)

    def on_click(self, _event: tk.Event) -> str:
        self.on_activate()
        self.text_widget.focus_set()
        return "break"

    def on_focus(self, _event: tk.Event) -> None:
        self.on_activate()
        self.render_screen()

    def on_resize(self, event: tk.Event) -> None:
        new_columns = max(int((event.width - 20) / self.char_width), 40)
        new_rows = max(int((event.height - 20) / self.line_height), 10)
        if new_columns == self.columns and new_rows == self.rows:
            return
        self.columns = new_columns
        self.rows = new_rows
        if self.pty_process is not None:
            try:
                self.pty_process.setwinsize(self.rows, self.columns)
            except Exception:
                pass
        if self.resize_after_id is not None:
            try:
                self.after_cancel(self.resize_after_id)
            except Exception:
                pass
        self.resize_after_id = self.after(25, self.apply_resize)

    def apply_resize(self) -> None:
        self.resize_after_id = None
        self.screen.resize(lines=self.rows, columns=self.columns)
        self.render_screen()

    def on_ctrl_c(self, _event: tk.Event) -> str:
        try:
            selected = self.text_widget.selection_get()
        except Exception:
            selected = ""
        if selected:
            self.copy_selection()
            return "break"
        self.current_input = ""
        self.is_command_line_mode = False
        if self.pty_process is not None:
            try:
                self.pty_process.sendintr()
            except Exception:
                pass
            self.write_text("\x03")
        else:
            self.write_text("\x03")
        if self.interrupt_after_id is not None:
            try:
                self.after_cancel(self.interrupt_after_id)
            except Exception:
                pass
        self.interrupt_after_id = self.after(700, self.ensure_interrupt_completed)
        return "break"

    def ensure_interrupt_completed(self) -> None:
        self.interrupt_after_id = None
        if self.is_command_line_mode or self.pty_process is None:
            return
        self.restart_shell()

    def copy_selection(self) -> None:
        try:
            selected = self.text_widget.selection_get()
        except Exception:
            selected = ""
        if selected:
            self.clipboard_clear()
            self.clipboard_append(selected)

    def show_context_menu(self, event: tk.Event) -> str:
        self.on_activate()
        self.text_widget.focus_set()
        try:
            has_selection = bool(self.text_widget.tag_ranges("sel"))
        except Exception:
            has_selection = False
        self.context_menu.entryconfigure("Copy", state="normal" if has_selection else "disabled")
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()
        return "break"

    def transform_command(self, command_text: str) -> str:
        lines: List[str] = []
        for line in command_text.split("\n"):
            stripped = line.strip()
            if stripped == "cd -":
                if self.previous_directory:
                    escaped = self.previous_directory.replace("'", "''")
                    lines.append(f"Set-Location -LiteralPath '{escaped}'")
                else:
                    lines.append("Write-Output 'No previous location.'")
                continue

            if re.match(r"^(git(?:\.exe)?\s+.*\blog\b.*)$", stripped, re.IGNORECASE) and "|" not in stripped:
                lines.append(f"{line} | more")
                continue

            lines.append(line)
        return "\n".join(lines)

    def _render_line_buffer(self, line_buffer: Dict[int, Any], keep_until: Optional[int] = None) -> str:
        rendered: List[str] = []
        is_wide = False
        for x in range(self.columns):
            if is_wide:
                is_wide = False
                continue
            char = line_buffer[x].data
            is_wide = wcwidth(char[0]) == 2 if char else False
            rendered.append(char)
        text = "".join(rendered)
        if keep_until is not None:
            keep_until = max(0, min(keep_until, len(text)))
            trimmed = text[:keep_until]
            return trimmed if trimmed else ""
        return text.rstrip()

    def _render_display_line(self, line: str, is_cursor_line: bool, cursor_col: int) -> str:
        if is_cursor_line:
            cursor_col = max(0, min(cursor_col, len(line)))
            return line[:cursor_col]
        return line.rstrip()

    def _is_view_scrolled_to_bottom(self) -> bool:
        try:
            first, last = self.text_widget.yview()
        except Exception:
            return True
        return last >= 0.999 or first <= 0.0 and last >= 0.999

    def render_screen(self) -> None:
        history_lines = [self._render_line_buffer(line) for line in self.screen.history.top]
        cursor_row = getattr(self.screen.cursor, "y", 0)
        cursor_col = getattr(self.screen.cursor, "x", 0)
        visible_lines = [
            self._render_display_line(line, row == cursor_row, cursor_col)
            for row, line in enumerate(self.screen.display)
        ]

        lines = history_lines + visible_lines
        content = "\n".join(lines)
        at_bottom = self._is_view_scrolled_to_bottom()
        current_view = self.text_widget.yview()

        self.tail_buffer = content[-2048:]
        prompt_match = self.prompt_pattern.search(self.tail_buffer)
        prompt_visible = bool(prompt_match and content.rstrip().endswith(">"))
        if prompt_match:
            new_directory = prompt_match.group(1).strip()
            if new_directory and new_directory != self.current_directory:
                self.previous_directory = self.current_directory
                self.current_directory = new_directory
        if prompt_visible:
            self.is_command_line_mode = True

        self.text_widget.delete("1.0", "end")
        self.text_widget.insert("1.0", content)

        insert_row = len(history_lines) + cursor_row + 1
        self.text_widget.mark_set("insert", f"{max(insert_row, 1)}.{cursor_col}")
        if at_bottom:
            self.text_widget.see("insert")
        else:
            try:
                self.text_widget.yview_moveto(current_view[0])
            except Exception:
                self.text_widget.see("insert")

    def on_paste(self, _event: tk.Event) -> str:
        try:
            clipboard = self.clipboard_get()
        except Exception:
            clipboard = ""
        if clipboard:
            if self.is_command_line_mode:
                self.current_input += clipboard
            self.write_text(clipboard)
        return "break"

    def on_key_press(self, event: tk.Event) -> str:
        self.on_activate()
        key_map = {
            "BackSpace": ("\x7f", 0),
            "Return": ("\r", None),
            "Tab": ("\t", None),
            "Escape": ("\x1b", 0),
            "Left": ("\x1b[D", None),
            "Right": ("\x1b[C", None),
            "Up": ("\x1b[A", None),
            "Down": ("\x1b[B", None),
            "Home": ("\x1b[H", None),
            "End": ("\x1b[F", None),
            "Delete": ("\x1b[3~", None),
            "Prior": ("\x1b[5~", None),
            "Next": ("\x1b[6~", None),
        }
        if event.keysym in key_map:
            payload, current_input_reset = key_map[event.keysym]
            if event.keysym == "BackSpace" and self.is_command_line_mode and self.current_input:
                self.current_input = self.current_input[:-1]
            elif event.keysym == "Return":
                normalized = self.current_input.strip()
                if normalized == "cd -" and self.previous_directory:
                    escaped = self.previous_directory.replace("'", "''")
                    self.erase_current_input_from_terminal()
                    payload = f"Set-Location -LiteralPath '{escaped}'\r"
                self.current_input = ""
                self.is_command_line_mode = False
            elif event.keysym == "Tab" and self.is_command_line_mode:
                completed = self.complete_input(self.current_input)
                if completed != self.current_input:
                    self.sync_current_input(completed)
                return "break"
            elif event.keysym in {"Escape"}:
                self.current_input = ""
            self.write_text(payload)
            return "break"

        if event.state & 0x4 and event.keysym.lower() == "l":
            self.write_text("cls\r")
            self.current_input = ""
            self.is_command_line_mode = False
            return "break"

        if event.char:
            if self.is_command_line_mode:
                self.current_input += event.char
            self.write_text(event.char)
            return "break"
        return "break"

    def destroy(self) -> None:
        if self.after_id is not None:
            try:
                self.after_cancel(self.after_id)
            except Exception:
                pass
        if self.interrupt_after_id is not None:
            try:
                self.after_cancel(self.interrupt_after_id)
            except Exception:
                pass
        if self.resize_after_id is not None:
            try:
                self.after_cancel(self.resize_after_id)
            except Exception:
                pass
        self.stop_shell()
        super().destroy()


class TerminalHost(ctk.CTkFrame):
    def __init__(self, master: ctk.CTkFrame, workspace: "TerminalWorkspace", initial_cwd: Optional[str] = None) -> None:
        super().__init__(master, corner_radius=8)
        self.workspace = workspace

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.grid(row=0, column=0, padx=8, pady=(8, 4), sticky="ew")
        toolbar.grid_columnconfigure(0, weight=1)

        self.title_label = ctk.CTkLabel(toolbar, text="PowerShell", font=ctk.CTkFont(size=13, weight="bold"))
        self.title_label.grid(row=0, column=0, sticky="w")

        button_box = ctk.CTkFrame(toolbar, fg_color="transparent")
        button_box.grid(row=0, column=1, sticky="e")

        ctk.CTkButton(button_box, text="Split H", width=72, command=lambda: self.workspace.split_active("horizontal")).pack(side="left", padx=(0, 6))
        ctk.CTkButton(button_box, text="Split V", width=72, command=lambda: self.workspace.split_active("vertical")).pack(side="left", padx=(0, 6))
        ctk.CTkButton(button_box, text="Close", width=70, fg_color="#c0392b", hover_color="#922b21", command=self.workspace.close_active).pack(side="left")

        self.terminal = EmbeddedTerminal(self, on_activate=lambda: self.workspace.set_active_host(self), initial_cwd=initial_cwd)
        self.terminal.grid(row=1, column=0, padx=8, pady=(0, 6), sticky="nsew")
        self._bind_activate_events()

    def _bind_activate_events(self) -> None:
        def activate(_event: tk.Event) -> str:
            self.workspace.set_active_host(self)
            self.terminal.text_widget.focus_set()
            return "break"

        for widget in (self, self.title_label, self.terminal):
            try:
                widget.bind("<Button-1>", activate, add="+")
            except Exception:
                pass

    def set_active(self, active: bool) -> None:
        self.terminal.set_active(active)


class TerminalWorkspace(ctk.CTkFrame):
    def __init__(self, master: ctk.CTkFrame, app: "QuickCommandApp") -> None:
        super().__init__(master, corner_radius=0)
        self.app = app
        self.root_widget: Optional[tk.Widget] = None
        self.active_host: Optional[TerminalHost] = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        initial_host = self.create_terminal_host(self)
        self.mount_root(initial_host)
        self.set_active_host(initial_host)

    def create_terminal_host(self, parent, initial_cwd: Optional[str] = None) -> TerminalHost:
        return TerminalHost(parent, self, initial_cwd=initial_cwd)

    def mount_root(self, widget: tk.Widget) -> None:
        self.root_widget = widget
        widget.grid(row=0, column=0, sticky="nsew")

    def _insert_into_parent(self, parent: tk.PanedWindow, index: int, widget: tk.Widget) -> None:
        try:
            parent.add(widget, stretch="always")
        except Exception:
            try:
                parent.add(widget, stretch="always")
            except Exception:
                parent.add(widget)

    def _rebalance_panedwindow(self, pane: tk.PanedWindow) -> None:
        try:
            panes = pane.panes()
        except Exception:
            return
        if len(panes) < 2:
            return
        try:
            orient = str(pane.cget("orient")).lower()
            pane.update_idletasks()
            if orient.endswith("vertical"):
                height = max(int(pane.winfo_height()), 2)
                pane.sash_place(0, 0, max(height // 2, 1))
            else:
                width = max(int(pane.winfo_width()), 2)
                pane.sash_place(0, max(width // 2, 1), 0)
        except Exception:
            pass

    def _pane_index(self, parent: tk.PanedWindow, child: tk.Widget) -> Optional[int]:
        target = str(child)
        for index, pane in enumerate(parent.panes()):
            if str(pane) == target:
                return index
        return None

    def _find_pane_parent(self, target: tk.Widget) -> Tuple[Optional[tk.PanedWindow], Optional[int]]:
        root = self.root_widget
        if root is None:
            return None, None

        def walk(widget: tk.Widget) -> Tuple[Optional[tk.PanedWindow], Optional[int]]:
            if isinstance(widget, tk.PanedWindow):
                index = self._pane_index(widget, target)
                if index is not None:
                    return widget, index
                for pane in widget.panes():
                    found_parent, found_index = walk(widget.nametowidget(str(pane)))
                    if found_parent is not None:
                        return found_parent, found_index
            return None, None

        if target == root and isinstance(root, tk.PanedWindow):
            return None, None
        return walk(root)

    def replace_widget(self, old_widget: tk.Widget, new_widget: tk.Widget) -> None:
        if old_widget == self.root_widget:
            old_widget.grid_forget()
            self.root_widget = new_widget
            new_widget.grid(row=0, column=0, sticky="nsew")
            return

        parent = old_widget.master
        if isinstance(parent, tk.PanedWindow):
            index = self._pane_index(parent, old_widget)
            if index is None:
                parent.add(new_widget)
                return
            parent.forget(old_widget)
            self._insert_into_parent(parent, index, new_widget)

    def set_active_host(self, host: TerminalHost) -> None:
        self.active_host = host
        for terminal_host in self.iter_hosts():
            terminal_host.set_active(terminal_host == host)
        self.app.set_active_terminal(host.terminal)

    def iter_hosts(self) -> List[TerminalHost]:
        hosts: List[TerminalHost] = []

        def walk(widget: tk.Widget) -> None:
            if isinstance(widget, TerminalHost):
                hosts.append(widget)
                return
            if isinstance(widget, tk.PanedWindow):
                for pane_name in widget.panes():
                    walk(widget.nametowidget(str(pane_name)))
            else:
                for child in widget.winfo_children():
                    if isinstance(child, (TerminalHost, tk.PanedWindow)):
                        walk(child)

        if self.root_widget is not None:
            walk(self.root_widget)
        return hosts

    def split_active(self, orientation: str) -> None:
        if self.active_host is None:
            return

        old_host = self.active_host
        inherited_cwd = old_host.terminal.current_directory or os.getcwd()
        parent, index = self._find_pane_parent(old_host)

        nested = tk.PanedWindow(
            parent if parent is not None else self,
            orient=tk.VERTICAL if orientation == "horizontal" else tk.HORIZONTAL,
            sashrelief=tk.RAISED,
            sashwidth=6,
            bd=0,
            bg="#3a4150",
        )

        if parent is None:
            self.replace_widget(old_host, nested)
        else:
            parent.forget(old_host)
            self._insert_into_parent(parent, index if index is not None else 0, nested)
        first_host = self.create_terminal_host(nested, initial_cwd=inherited_cwd)
        second_host = self.create_terminal_host(nested, initial_cwd=inherited_cwd)

        nested.add(first_host, stretch="always")
        nested.add(second_host, stretch="always")
        try:
            nested.paneconfigure(first_host, stretch="always")
            nested.paneconfigure(second_host, stretch="always")
        except Exception:
            pass
        try:
            nested.update_idletasks()
            (parent if parent is not None else self).update_idletasks()
        except Exception:
            pass
        try:
            if parent is not None:
                self._rebalance_panedwindow(parent)
            self._rebalance_panedwindow(nested)
        except Exception:
            pass
        old_host.destroy()
        self.set_active_host(second_host)

    def close_active(self) -> None:
        if self.active_host is None:
            return
        if len(self.iter_hosts()) == 1:
            self.active_host.terminal.send_command("Clear-Host")
            return

        host = self.active_host
        parent, index = self._find_pane_parent(host)
        if not isinstance(parent, tk.PanedWindow):
            return

        if index is None:
            return
        parent.forget(host)
        host.destroy()

        remaining = list(parent.panes())
        if len(remaining) == 1:
            survivor = parent.nametowidget(str(remaining[0]))
            if isinstance(survivor, TerminalHost):
                self.set_active_host(survivor)
            elif isinstance(survivor, tk.PanedWindow):
                child_hosts = self.iter_hosts()
                if child_hosts:
                    self.set_active_host(child_hosts[0])
            try:
                self._rebalance_panedwindow(parent)
            except Exception:
                pass
            return

        next_index = min(index, len(remaining) - 1)
        next_widget = parent.nametowidget(str(remaining[next_index]))
        if isinstance(next_widget, TerminalHost):
            self.set_active_host(next_widget)
        elif isinstance(next_widget, tk.PanedWindow):
            child_hosts = self.iter_hosts()
            if child_hosts:
                self.set_active_host(child_hosts[0])

    def get_active_terminal(self) -> Optional[EmbeddedTerminal]:
        if self.active_host is None:
            return None
        return self.active_host.terminal


class QuickCommandWindow(ctk.CTkToplevel):
    TOKENS = {
        "bg": "#1e1e1e",
        "panel": "#252526",
        "panel_alt": "#202020",
        "panel_soft": "#2f2f33",
        "border": "#3c3c3c",
        "text": "#ffffff",
        "text_dim": "#ffffff",
        "muted": "#ffffff",
        "accent": "#3794ff",
        "accent_soft": "#094771",
        "hover": "#2a2d2e",
        "code_bg": "#1e1e1e",
        "selected_text": "#ffffff",
    }

    def __init__(self, app: "QuickCommandApp") -> None:
        super().__init__(app)
        self.app = app
        self.selected_group_id: Optional[str] = None
        self.selected_item_id: Optional[str] = None
        self.selected_command_id: Optional[str] = None

        self.title("Quick Command")
        self.geometry("1180x720")
        self.minsize(980, 620)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.configure(fg_color=self.TOKENS["bg"])

        self.group_menu = tk.Menu(self, tearoff=0)
        self.item_menu = tk.Menu(self, tearoff=0)
        self.command_menu = tk.Menu(self, tearoff=0)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.shell = ctk.CTkFrame(self, fg_color=self.TOKENS["bg"], corner_radius=0)
        self.shell.grid(row=0, column=0, sticky="nsew")
        self.shell.grid_columnconfigure(0, weight=0)
        self.shell.grid_columnconfigure(1, weight=0)
        self.shell.grid_columnconfigure(2, weight=1)
        self.shell.grid_rowconfigure(1, weight=1)

        self.create_header()
        self.create_columns()
        self.configure_menus()
        self.restore_selection()
        self.refresh_all()

    def debug_log(self, message: str) -> None:
        try:
            self.app.append_status(f"[QuickCommand] {message}")
        except Exception:
            pass

    def describe_text(self, value: Any) -> str:
        if value is None:
            return "None"
        if isinstance(value, str):
            return f"repr={value!r} len={len(value)} stripped={value.strip()!r}"
        return f"type={type(value).__name__} repr={value!r}"

    def create_header(self) -> None:
        header = ctk.CTkFrame(self.shell, fg_color=self.TOKENS["panel_alt"], corner_radius=0, height=32)
        header.grid(row=0, column=0, columnspan=3, sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(header, text="QUICK COMMAND", text_color=self.TOKENS["text_dim"], font=ctk.CTkFont(size=11, weight="bold")).grid(row=0, column=0, padx=(10, 8), pady=5, sticky="w")
        ctk.CTkLabel(header, text="Explorer / List / Preview", text_color=self.TOKENS["selected_text"], font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=1, pady=5, sticky="w")

        toolbar = ctk.CTkFrame(header, fg_color=self.TOKENS["panel_alt"])
        toolbar.grid(row=0, column=2, padx=10, pady=2, sticky="e")
        self.header_new_group = self.make_action_button(toolbar, "New Group", self.add_group)
        self.header_new_group.pack(side="left", padx=(0, 6))
        self.header_new_item = self.make_action_button(toolbar, "New Item", self.add_item)
        self.header_new_item.pack(side="left", padx=(0, 6))
        self.header_new_command = self.make_action_button(toolbar, "New Cmd", self.add_command)
        self.header_new_command.pack(side="left", padx=(0, 6))
        self.header_run_all = self.make_action_button(toolbar, "Run All", self.run_all_commands)
        self.header_run_all.pack(side="left")

    def create_columns(self) -> None:
        self.group_panel = self.make_panel(self.shell, 172)
        self.group_panel.grid(row=1, column=0, padx=(8, 4), pady=8, sticky="nsew")
        self.group_panel.grid_columnconfigure(0, weight=1)
        self.group_panel.grid_rowconfigure(1, weight=1)

        self.item_panel = self.make_panel(self.shell, 198)
        self.item_panel.grid(row=1, column=1, padx=4, pady=8, sticky="nsew")
        self.item_panel.grid_columnconfigure(0, weight=1)
        self.item_panel.grid_rowconfigure(1, weight=1)

        self.command_panel = self.make_panel(self.shell, 0)
        self.command_panel.grid(row=1, column=2, padx=(4, 8), pady=8, sticky="nsew")
        self.command_panel.grid_columnconfigure(0, weight=1)
        self.command_panel.grid_rowconfigure(2, weight=1)
        self.command_panel.grid_rowconfigure(4, weight=1)

        self.group_title = self.make_section_header(self.group_panel, "GROUPS", ("New", self.add_group))
        self.group_scroll = self.make_scroll(self.group_panel)

        self.item_title = self.make_section_header(self.item_panel, "ITEMS", ("New", self.add_item))
        self.item_scroll = self.make_scroll(self.item_panel)

        self.create_detail_section()

    def create_detail_section(self) -> None:
        title_wrap = ctk.CTkFrame(self.command_panel, fg_color=self.TOKENS["panel_alt"])
        title_wrap.grid(row=0, column=0, padx=10, pady=(8, 3), sticky="ew")
        title_wrap.grid_columnconfigure(0, weight=1)

        self.command_title = ctk.CTkLabel(title_wrap, text="No Selection", text_color=self.TOKENS["text"], font=ctk.CTkFont(size=15, weight="bold"), anchor="w")
        self.command_title.grid(row=0, column=0, sticky="w")

        self.command_subtitle = ctk.CTkLabel(title_wrap, text="Choose a group and item to inspect commands.", text_color=self.TOKENS["text_dim"], font=ctk.CTkFont(size=10), anchor="w")
        self.command_subtitle.grid(row=1, column=0, pady=(2, 0), sticky="w")

        actions = ctk.CTkFrame(title_wrap, fg_color=self.TOKENS["panel_alt"])
        actions.grid(row=0, column=1, rowspan=2, sticky="e")
        self.command_new_button = self.make_action_button(actions, "New Cmd", self.add_command)
        self.command_new_button.pack(side="left", padx=(0, 6))
        self.command_run_all_button = self.make_action_button(actions, "Run All", self.run_all_commands)
        self.command_run_all_button.pack(side="left", padx=(0, 6))
        self.command_run_button = self.make_action_button(actions, "Run", self.run_selected_command)
        self.command_run_button.pack(side="left", padx=(0, 6))
        self.command_copy_button = self.make_action_button(actions, "Copy", self.copy_selected_command)
        self.command_copy_button.pack(side="left", padx=(0, 6))
        self.command_edit_button = self.make_action_button(actions, "Edit", self.edit_selected_command)
        self.command_edit_button.pack(side="left", padx=(0, 6))
        self.command_delete_button = self.make_action_button(actions, "Delete", self.delete_selected_command)
        self.command_delete_button.pack(side="left")

        list_header = ctk.CTkFrame(self.command_panel, fg_color=self.TOKENS["panel_alt"])
        list_header.grid(row=1, column=0, padx=10, pady=(0, 3), sticky="ew")
        ctk.CTkLabel(list_header, text="COMMANDS", text_color=self.TOKENS["text_dim"], font=ctk.CTkFont(size=10, weight="bold")).pack(side="left")

        self.command_scroll = ctk.CTkScrollableFrame(self.command_panel, fg_color=self.TOKENS["panel"], corner_radius=0)
        self.command_scroll.grid(row=2, column=0, padx=8, pady=(0, 4), sticky="nsew")
        self.command_scroll.grid_columnconfigure(0, weight=1)

        preview_header = ctk.CTkFrame(self.command_panel, fg_color=self.TOKENS["panel_alt"])
        preview_header.grid(row=3, column=0, padx=10, pady=(0, 3), sticky="ew")
        ctk.CTkLabel(preview_header, text="PREVIEW", text_color=self.TOKENS["text_dim"], font=ctk.CTkFont(size=10, weight="bold")).pack(side="left")

        preview_shell = ctk.CTkFrame(self.command_panel, fg_color=self.TOKENS["code_bg"], corner_radius=8)
        preview_shell.grid(row=4, column=0, padx=8, pady=(0, 6), sticky="nsew")
        preview_shell.grid_columnconfigure(0, weight=1)
        preview_shell.grid_rowconfigure(0, weight=1)

        self.command_preview = ctk.CTkTextbox(preview_shell, fg_color=self.TOKENS["code_bg"], text_color=self.TOKENS["selected_text"], border_width=0, font=ctk.CTkFont(family="Consolas", size=11), wrap="none")
        self.command_preview.grid(row=0, column=0, sticky="nsew")
        self.command_preview.configure(state="disabled")

    def make_panel(self, parent, width: int) -> ctk.CTkFrame:
        panel = ctk.CTkFrame(parent, fg_color=self.TOKENS["panel"], corner_radius=8, border_width=1, border_color=self.TOKENS["border"], width=width)
        if width:
            panel.grid_propagate(False)
        return panel

    def make_scroll(self, parent) -> ctk.CTkScrollableFrame:
        scroll = ctk.CTkScrollableFrame(parent, fg_color=self.TOKENS["panel"], corner_radius=0)
        scroll.grid(row=1, column=0, padx=5, pady=(0, 3), sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)
        return scroll

    def make_section_header(self, parent, title: str, action: Tuple[str, Any]) -> ctk.CTkLabel:
        header = ctk.CTkFrame(parent, fg_color=self.TOKENS["panel_alt"])
        header.grid(row=0, column=0, padx=8, pady=(8, 2), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        label = ctk.CTkLabel(header, text=title, text_color=self.TOKENS["text_dim"], font=ctk.CTkFont(size=10, weight="bold"))
        label.grid(row=0, column=0, sticky="w")
        self.make_action_button(header, action[0], action[1]).grid(row=0, column=1, sticky="e")
        return label

    def make_action_button(self, parent, text: str, command) -> ctk.CTkButton:
        return ctk.CTkButton(parent, text=text, command=command, height=20, width=50, corner_radius=4, fg_color=self.TOKENS["panel_soft"], hover_color=self.TOKENS["hover"], text_color=self.TOKENS["selected_text"], border_width=0, font=ctk.CTkFont(size=10, weight="bold"))

    def configure_menus(self) -> None:
        self.group_menu.add_command(label="Rename Group", command=self.rename_selected_group)
        self.group_menu.add_command(label="Delete Group", command=self.delete_selected_group)
        self.item_menu.add_command(label="Rename Item", command=self.rename_selected_item)
        self.item_menu.add_command(label="Delete Item", command=self.delete_selected_item)
        self.command_menu.add_command(label="Run", command=self.run_selected_command)
        self.command_menu.add_command(label="Copy", command=self.copy_selected_command)
        self.command_menu.add_command(label="Edit", command=self.edit_selected_command)
        self.command_menu.add_separator()
        self.command_menu.add_command(label="Delete", command=self.delete_selected_command)

    def restore_selection(self) -> None:
        groups = self.app.data.get("groups", [])
        self.debug_log(f"restore_selection groups={len(groups)} selected_group_id={self.selected_group_id!r} selected_item_id={self.selected_item_id!r} selected_command_id={self.selected_command_id!r}")
        if not groups:
            self.selected_group_id = None
            self.selected_item_id = None
            self.selected_command_id = None
            return

        if not any(group["id"] == self.selected_group_id for group in groups):
            self.selected_group_id = groups[0]["id"]

        group = self.get_selected_group()
        if not group:
            self.selected_item_id = None
            self.selected_command_id = None
            return

        items = group.get("items", [])
        if not items:
            self.selected_item_id = None
            self.selected_command_id = None
            return

        if not any(item["id"] == self.selected_item_id for item in items):
            self.selected_item_id = items[0]["id"]

        item = self.get_selected_item()
        if not item:
            self.selected_command_id = None
            return

        commands = item.get("commands", [])
        if not commands:
            self.selected_command_id = None
            return

        if not any(command["id"] == self.selected_command_id for command in commands):
            self.selected_command_id = commands[0]["id"]

    def refresh_all(self) -> None:
        self.restore_selection()
        self.render_groups()
        self.render_items()
        self.render_commands()
        has_group = self.get_selected_group() is not None
        has_item = self.get_selected_item() is not None
        has_command = self.get_selected_command() is not None
        self.header_new_item.configure(state="normal" if has_group else "disabled")
        self.header_new_command.configure(state="normal" if has_item else "disabled")
        self.header_run_all.configure(state="normal" if has_item else "disabled")
        self.command_new_button.configure(state="normal" if has_item else "disabled")
        self.command_run_all_button.configure(state="normal" if has_item else "disabled")
        self.command_run_button.configure(state="normal" if has_command else "disabled")
        self.command_copy_button.configure(state="normal" if has_command else "disabled")
        self.command_edit_button.configure(state="normal" if has_command else "disabled")
        self.command_delete_button.configure(state="normal" if has_command else "disabled")

    def clear_frame(self, frame: ctk.CTkScrollableFrame) -> None:
        for child in frame.winfo_children():
            child.destroy()

    def get_selected_group(self) -> Optional[Dict[str, Any]]:
        for group in self.app.data.get("groups", []):
            if group["id"] == self.selected_group_id:
                return group
        return None

    def get_selected_item(self) -> Optional[Dict[str, Any]]:
        group = self.get_selected_group()
        if not group:
            return None
        for item in group.get("items", []):
            if item["id"] == self.selected_item_id:
                return item
        return None

    def get_selected_command(self) -> Optional[Dict[str, Any]]:
        item = self.get_selected_item()
        if not item:
            return None
        for command in item.get("commands", []):
            if command["id"] == self.selected_command_id:
                return command
        return None

    def find_item_and_parent(self, item_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        for group in self.app.data.get("groups", []):
            for item in group.get("items", []):
                if item["id"] == item_id:
                    return group, item
        return None, None

    def find_command_and_parent(self, command_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        for group in self.app.data.get("groups", []):
            for item in group.get("items", []):
                for command in item.get("commands", []):
                    if command["id"] == command_id:
                        return group, item, command
        return None, None, None

    def show_menu(self, menu: tk.Menu, event: tk.Event) -> None:
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def select_group(self, group_id: str) -> None:
        self.selected_group_id = group_id
        group = self.get_selected_group()
        self.debug_log(
            f"select_group group_id={group_id!r} resolved_name={self.describe_text(group.get('name') if group else None)} items={len(group.get('items', [])) if group else 0}"
        )
        self.selected_item_id = group["items"][0]["id"] if group and group.get("items") else None
        item = self.get_selected_item()
        self.selected_command_id = item["commands"][0]["id"] if item and item.get("commands") else None
        self.refresh_all()

    def select_item(self, item_id: str) -> None:
        group, item = self.find_item_and_parent(item_id)
        if not group or not item:
            return
        self.debug_log(
            f"select_item item_id={item_id!r} group_name={self.describe_text(group.get('name'))} item_name={self.describe_text(item.get('name'))} commands={len(item.get('commands', []))}"
        )
        self.selected_group_id = group["id"]
        self.selected_item_id = item["id"]
        self.selected_command_id = item["commands"][0]["id"] if item.get("commands") else None
        self.refresh_all()

    def select_command(self, command_id: str) -> None:
        _group, item, command = self.find_command_and_parent(command_id)
        if not item or not command:
            return
        self.debug_log(
            f"select_command command_id={command_id!r} item_name={self.describe_text(item.get('name'))} command={self.describe_text(command.get('command'))}"
        )
        self.selected_item_id = item["id"]
        self.selected_command_id = command["id"]
        self.refresh_all()

    def create_list_row(self, parent, title: str, subtitle: str, selected: bool, command, menu_handler) -> ctk.CTkFrame:
        display_title = title.strip() if isinstance(title, str) else ""
        if not display_title:
            self.debug_log(f"empty list title selected={selected} title={self.describe_text(title)} subtitle={self.describe_text(subtitle)}")
            display_title = "(empty)"

        row_bg = self.TOKENS["accent_soft"] if selected else self.TOKENS["panel_alt"]
        row_hover = "#0b5aa7" if selected else self.TOKENS["panel_soft"]

        row = ctk.CTkFrame(
            parent,
            fg_color=row_bg,
            corner_radius=4,
            height=30,
            border_width=1 if selected else 0,
            border_color=self.TOKENS["accent"] if selected else self.TOKENS["panel_alt"],
        )
        row.grid_propagate(False)

        accent = ctk.CTkFrame(
            row,
            fg_color=self.TOKENS["accent"] if selected else self.TOKENS["panel_soft"],
            width=2,
            corner_radius=2,
        )
        accent.place(x=0, rely=0.08, relheight=0.84)

        row_text = f"{display_title}    {subtitle}"
        text_button = ctk.CTkButton(
            row,
            text=row_text,
            command=command,
            fg_color=row_bg,
            hover_color=row_hover,
            text_color=self.TOKENS["selected_text"],
            width=10,
            border_width=0,
            corner_radius=3,
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
            height=26,
        )
        text_button.place(x=10, y=2, relwidth=0.93)

        # Keep simple left-click handling on row background and accent bar.
        for widget in (row, accent):
            widget.bind("<Button-1>", lambda _event, cb=command: cb())
            widget.bind("<Double-Button-1>", lambda _event, cb=command: cb())
            widget.bind("<Button-3>", menu_handler)

        # Right click menu on the main row text/button.
        text_button.bind("<Button-1>", lambda _event, cb=command: cb())
        text_button.bind("<Double-Button-1>", lambda _event, cb=command: cb())
        text_button.bind("<Button-3>", menu_handler)

        return row

    def render_groups(self) -> None:
        self.clear_frame(self.group_scroll)
        groups = self.app.data.get("groups", [])
        self.debug_log(f"render_groups count={len(groups)} selected_group_id={self.selected_group_id!r}")
        if not groups:
            ctk.CTkLabel(self.group_scroll, text="No groups yet", text_color=self.TOKENS["text_dim"], font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=0, padx=10, pady=14, sticky="w")
            return
        for index, group in enumerate(groups):
            self.debug_log(
                f"group[{index}] id={group.get('id')!r} name={self.describe_text(group.get('name'))} items={len(group.get('items', []))}"
            )
            row = self.create_list_row(self.group_scroll, group["name"], f"{len(group.get('items', []))} items", group["id"] == self.selected_group_id, lambda gid=group["id"]: self.select_group(gid), lambda event, gid=group["id"]: self.on_group_menu(event, gid))
            row.grid(row=index, column=0, padx=3, pady=1, sticky="ew")

    def render_items(self) -> None:
        self.clear_frame(self.item_scroll)
        group = self.get_selected_group()
        self.debug_log(f"render_items selected_group={self.describe_text(group.get('name')) if group else 'None'} selected_group_id={self.selected_group_id!r} selected_item_id={self.selected_item_id!r}")
        self.item_title.configure(text=f"ITEMS | {group['name']}" if group else "ITEMS")
        if not group:
            ctk.CTkLabel(self.item_scroll, text="Select a group", text_color=self.TOKENS["text_dim"], font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=0, padx=10, pady=14, sticky="w")
            return
        items = group.get("items", [])
        self.debug_log(f"items_in_group={len(items)} group_name={self.describe_text(group.get('name'))}")
        if not items:
            ctk.CTkLabel(self.item_scroll, text="No items", text_color=self.TOKENS["text_dim"], font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=0, padx=10, pady=14, sticky="w")
            return
        for index, item in enumerate(items):
            self.debug_log(
                f"item[{index}] id={item.get('id')!r} name={self.describe_text(item.get('name'))} commands={len(item.get('commands', []))}"
            )
            row = self.create_list_row(self.item_scroll, item["name"], f"{len(item.get('commands', []))} commands", item["id"] == self.selected_item_id, lambda iid=item["id"]: self.select_item(iid), lambda event, iid=item["id"]: self.on_item_menu(event, iid))
            row.grid(row=index, column=0, padx=3, pady=1, sticky="ew")

    def render_commands(self) -> None:
        self.clear_frame(self.command_scroll)
        group = self.get_selected_group()
        item = self.get_selected_item()
        command = self.get_selected_command()
        self.debug_log(
            f"render_commands group={self.describe_text(group.get('name')) if group else 'None'} item={self.describe_text(item.get('name')) if item else 'None'} selected_command_id={self.selected_command_id!r}"
        )
        if not group or not item:
            self.command_title.configure(text="No Selection")
            self.command_subtitle.configure(text="Choose a group and item to inspect commands.")
            self.set_preview_text("")
            ctk.CTkLabel(self.command_scroll, text="Commands will appear here", text_color=self.TOKENS["text_dim"], font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=0, padx=10, pady=14, sticky="w")
            return

        commands = item.get("commands", [])
        self.debug_log(f"commands_in_item={len(commands)} item_name={self.describe_text(item.get('name'))}")
        self.command_title.configure(text=item["name"])
        self.command_subtitle.configure(text=f"{group['name']} | {len(commands)} commands")
        if not commands:
            self.set_preview_text("")
            ctk.CTkLabel(self.command_scroll, text="No commands yet", text_color=self.TOKENS["text_dim"], font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=0, padx=10, pady=14, sticky="w")
            return

        for index, entry in enumerate(commands):
            self.debug_log(
                f"command[{index}] id={entry.get('id')!r} command={self.describe_text(entry.get('command'))}"
            )
            row = self.create_list_row(self.command_scroll, entry["command"].splitlines()[0][:72] or "(empty)", f"#{index + 1} | {len(entry['command'].splitlines())} lines", entry["id"] == self.selected_command_id, lambda cid=entry["id"]: self.select_command(cid), lambda event, cid=entry["id"]: self.on_command_menu(event, cid))
            row.grid(row=index, column=0, padx=3, pady=1, sticky="ew")
        self.set_preview_text(command["command"] if command else "")

    def set_preview_text(self, text: str) -> None:
        self.command_preview.configure(state="normal")
        self.command_preview.delete("1.0", "end")
        if text:
            self.command_preview.insert("1.0", text)
        self.command_preview.configure(state="disabled")

    def on_group_menu(self, event: tk.Event, group_id: str) -> None:
        self.select_group(group_id)
        self.show_menu(self.group_menu, event)

    def on_item_menu(self, event: tk.Event, item_id: str) -> None:
        self.select_item(item_id)
        self.show_menu(self.item_menu, event)

    def on_command_menu(self, event: tk.Event, command_id: str) -> None:
        self.select_command(command_id)
        self.show_menu(self.command_menu, event)

    def add_group(self) -> None:
        name = SingleLineDialog.ask(self, "New Group", "Enter group name:")
        if not name:
            return
        new_group = {"id": uuid.uuid4().hex, "name": name, "items": []}
        self.app.data["groups"].append(new_group)
        self.selected_group_id = new_group["id"]
        self.selected_item_id = None
        self.selected_command_id = None
        self.app.save_data()
        self.refresh_all()
        self.app.append_status(f"Created group: {name}")

    def rename_selected_group(self) -> None:
        if self.selected_group_id:
            self.rename_group(self.selected_group_id)

    def rename_group(self, group_id: str) -> None:
        group = next((group for group in self.app.data.get("groups", []) if group["id"] == group_id), None)
        if not group:
            return
        new_name = SingleLineDialog.ask(self, "Rename Group", "Enter new group name:", group["name"])
        if not new_name:
            return
        old_name = group["name"]
        group["name"] = new_name
        self.app.save_data()
        self.refresh_all()
        self.app.append_status(f"Renamed group: {old_name} -> {new_name}")

    def delete_group(self, group_id: str) -> None:
        groups = self.app.data.get("groups", [])
        target = next((group for group in groups if group["id"] == group_id), None)
        if not target:
            return
        if not messagebox.askyesno("Delete Group", f"Delete group '{target['name']}'?\nAll nested items and commands will be removed.", parent=self):
            return
        self.app.data["groups"] = [group for group in groups if group["id"] != group_id]
        if self.selected_group_id == group_id:
            self.selected_group_id = None
            self.selected_item_id = None
            self.selected_command_id = None
        self.app.save_data()
        self.refresh_all()
        self.app.append_status(f"Deleted group: {target['name']}")

    def delete_selected_group(self) -> None:
        if self.selected_group_id:
            self.delete_group(self.selected_group_id)

    def add_item(self) -> None:
        group = self.get_selected_group()
        if not group:
            messagebox.showwarning("Warning", "Please select a group first.", parent=self)
            return
        name = SingleLineDialog.ask(self, "New Item", "Enter item name:")
        if not name:
            return
        new_item = {"id": uuid.uuid4().hex, "name": name, "commands": []}
        group["items"].append(new_item)
        self.selected_item_id = new_item["id"]
        self.selected_command_id = None
        self.app.save_data()
        self.refresh_all()
        self.app.append_status(f"Created item '{name}' in group '{group['name']}'")

    def rename_selected_item(self) -> None:
        if self.selected_item_id:
            self.rename_item(self.selected_item_id)

    def rename_item(self, item_id: str) -> None:
        _group, item = self.find_item_and_parent(item_id)
        if not item:
            return
        new_name = SingleLineDialog.ask(self, "Rename Item", "Enter new item name:", item["name"])
        if not new_name:
            return
        old_name = item["name"]
        item["name"] = new_name
        self.app.save_data()
        self.refresh_all()
        self.app.append_status(f"Renamed item: {old_name} -> {new_name}")

    def delete_item(self, item_id: str) -> None:
        group, item = self.find_item_and_parent(item_id)
        if not group or not item:
            return
        if not messagebox.askyesno("Delete Item", f"Delete item '{item['name']}'?\nAll nested commands will be removed.", parent=self):
            return
        group["items"] = [candidate for candidate in group.get("items", []) if candidate["id"] != item_id]
        if self.selected_item_id == item_id:
            self.selected_item_id = None
            self.selected_command_id = None
        self.app.save_data()
        self.refresh_all()
        self.app.append_status(f"Deleted item: {item['name']}")

    def delete_selected_item(self) -> None:
        if self.selected_item_id:
            self.delete_item(self.selected_item_id)

    def add_command(self) -> None:
        item = self.get_selected_item()
        if not item:
            messagebox.showwarning("Warning", "Please select an item first.", parent=self)
            return
        command_text = CommandDialog.ask(self, "Add Command")
        if not command_text:
            return
        new_command = {"id": uuid.uuid4().hex, "command": command_text}
        item["commands"].append(new_command)
        self.selected_command_id = new_command["id"]
        self.app.save_data()
        self.refresh_all()
        self.app.append_status(f"Added command to item '{item['name']}'")

    def edit_selected_command(self) -> None:
        if self.selected_command_id:
            self.edit_command(self.selected_command_id)

    def edit_command(self, command_id: str) -> None:
        _group, item, command = self.find_command_and_parent(command_id)
        if not item or not command:
            return
        new_text = CommandDialog.ask(self, "Edit Command", command["command"])
        if not new_text:
            return
        command["command"] = new_text
        self.app.save_data()
        self.refresh_all()
        self.app.append_status(f"Updated command in item '{item['name']}'")

    def delete_command(self, command_id: str) -> None:
        _group, item, command = self.find_command_and_parent(command_id)
        if not item or not command:
            return
        if not messagebox.askyesno("Delete Command", "Delete this command?", parent=self):
            return
        item["commands"] = [candidate for candidate in item.get("commands", []) if candidate["id"] != command_id]
        if self.selected_command_id == command_id:
            self.selected_command_id = item["commands"][0]["id"] if item.get("commands") else None
        self.app.save_data()
        self.refresh_all()
        self.app.append_status(f"Deleted command: {command['command'].splitlines()[0][:60]}")

    def delete_selected_command(self) -> None:
        if self.selected_command_id:
            self.delete_command(self.selected_command_id)

    def copy_selected_command(self) -> None:
        command = self.get_selected_command()
        if command:
            self.copy_command(command["command"])

    def copy_command(self, command_text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(command_text)
        self.app.append_status("Command copied to clipboard.")

    def run_selected_command(self) -> None:
        item = self.get_selected_item()
        command = self.get_selected_command()
        if not item or not command:
            return
        commands = item.get("commands", [])
        index = next((idx + 1 for idx, entry in enumerate(commands) if entry["id"] == command["id"]), 1)
        self.app.send_to_active_terminal(command["command"], f"{item['name']} / Command {index}")

    def run_all_commands(self) -> None:
        item = self.get_selected_item()
        if not item:
            messagebox.showwarning("Warning", "Please select an item first.", parent=self)
            return
        commands = item.get("commands", [])
        if not commands:
            return
        for index, command in enumerate(commands, start=1):
            self.app.send_to_active_terminal(command["command"], f"{item['name']} / Command {index}")

    def on_close(self) -> None:
        self.withdraw()


class QuickCommandApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.report_callback_exception = self.on_tk_exception

        self.base_dir = app_directory()
        self.data_file = os.path.join(self.base_dir, "data.json")
        self.store = DataStore(self.data_file)
        self.data = self.store.load()

        self.quick_command_window: Optional[QuickCommandWindow] = None
        self.active_terminal: Optional[EmbeddedTerminal] = None
        self.tab_counter = 0
        self.tab_workspaces: Dict[str, TerminalWorkspace] = {}

        self.title("PowerShell Workspace")
        self.geometry("1600x960")
        self.minsize(1240, 760)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.create_toolbar()
        self.create_workspace()
        self.create_initial_tab()
        self.deiconify()

    def create_toolbar(self) -> None:
        self.toolbar = ctk.CTkFrame(self, height=60, corner_radius=0)
        self.toolbar.grid(row=0, column=0, sticky="ew")
        self.toolbar.grid_columnconfigure(4, weight=1)

        ctk.CTkButton(self.toolbar, text="+ New Tab", width=110, command=self.add_tab).grid(row=0, column=0, padx=(14, 8), pady=12)
        ctk.CTkButton(self.toolbar, text="Close Tab", width=100, command=self.close_current_tab).grid(row=0, column=1, padx=(0, 8), pady=12)
        ctk.CTkButton(self.toolbar, text="Split H", width=90, command=lambda: self.split_current_workspace("horizontal")).grid(row=0, column=2, padx=(0, 8), pady=12)
        ctk.CTkButton(self.toolbar, text="Split V", width=90, command=lambda: self.split_current_workspace("vertical")).grid(row=0, column=3, padx=(0, 8), pady=12)
        ctk.CTkButton(self.toolbar, text="Quick Command", width=120, command=self.open_quick_command_window).grid(row=0, column=5, padx=(8, 14), pady=12, sticky="e")

    def create_workspace(self) -> None:
        self.workspace_container = ctk.CTkFrame(self, corner_radius=0)
        self.workspace_container.grid(row=1, column=0, sticky="nsew")
        self.workspace_container.grid_columnconfigure(0, weight=1)
        self.workspace_container.grid_rowconfigure(0, weight=1)

        self.notebook = ttk.Notebook(self.workspace_container)
        self.notebook.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

    def create_initial_tab(self) -> None:
        self.add_tab()

    def add_tab(self) -> None:
        self.tab_counter += 1
        frame = ctk.CTkFrame(self.notebook, corner_radius=0)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)

        workspace = TerminalWorkspace(frame, self)
        workspace.grid(row=0, column=0, sticky="nsew")

        tab_title = f"Tab {self.tab_counter}"
        self.notebook.add(frame, text=tab_title)
        self.tab_workspaces[str(frame)] = workspace
        self.notebook.select(frame)
        self.set_active_terminal(workspace.get_active_terminal())
        self.append_status(f"Opened {tab_title}")

    def close_current_tab(self) -> None:
        current = self.notebook.select()
        if not current:
            return
        if len(self.notebook.tabs()) == 1:
            return

        workspace = self.tab_workspaces.pop(current, None)
        if workspace is not None:
            workspace.destroy()
        self.notebook.forget(current)
        self.append_status("Closed current tab")
        self.on_tab_changed()

    def get_current_workspace(self) -> Optional[TerminalWorkspace]:
        current = self.notebook.select()
        if not current:
            return None
        return self.tab_workspaces.get(current)

    def on_tab_changed(self, _event: object = None) -> None:
        workspace = self.get_current_workspace()
        if workspace is not None:
            self.set_active_terminal(workspace.get_active_terminal())

    def set_active_terminal(self, terminal: Optional[EmbeddedTerminal]) -> None:
        self.active_terminal = terminal

    def split_current_workspace(self, orientation: str) -> None:
        workspace = self.get_current_workspace()
        if workspace is None:
            return
        workspace.split_active(orientation)
        self.append_status(f"Split active terminal {orientation}.")

    def open_quick_command_window(self) -> None:
        window = self.quick_command_window
        if window is None or not window.winfo_exists():
            try:
                window = QuickCommandWindow(self)
            except Exception as error:
                self.quick_command_window = None
                self.append_status(f"Failed to open Quick Command window: {error}")
                messagebox.showerror("Quick Command", f"Failed to open Quick Command window:\n{error}", parent=self)
                return
            self.quick_command_window = window

        window.deiconify()
        window.lift()
        window.focus_force()
        window.refresh_all()
        self.append_status("Opened Quick Command window.")

    def save_data(self) -> None:
        self.store.save(self.data)

    def send_to_active_terminal(self, command_text: str, label: str) -> None:
        if self.active_terminal is None:
            messagebox.showwarning("Warning", "No active terminal is available.", parent=self)
            return
        self.active_terminal.send_command(command_text)
        self.append_status(f"Sent to terminal: {label}")

    def on_tk_exception(self, exc: type[BaseException], val: BaseException, tb: Any) -> None:
        details = "".join(traceback.format_exception(exc, val, tb))
        write_startup_log(details)
        try:
            messagebox.showerror("Quick Command", details, parent=self)
        except Exception:
            pass

    def append_status(self, message: str) -> None:
        _ = message

    def clear_status_log(self) -> None:
        return


if __name__ == "__main__":
    write_startup_log("=== launch ===")
    try:
        app = QuickCommandApp()
        write_startup_log("app initialized")
        app.mainloop()
        write_startup_log("mainloop exited")
    except Exception:
        write_startup_log("".join(traceback.format_exc()))
        raise
