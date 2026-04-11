import json
import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
import uuid
from tkinter import messagebox, ttk
from typing import Any, Dict, List, Optional, Tuple

import customtkinter as ctk
import pyte
from pyte.screens import wcwidth
from winpty import PtyProcess


ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


def app_directory() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


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
        os.replace(temp_path, self.file_path)


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
            font=ctk.CTkFont(size=16, weight="bold"),
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
    def __init__(self, master: ctk.CTkFrame, on_activate) -> None:
        super().__init__(master, corner_radius=10, fg_color=("#f4f6f8", "#11161e"))
        self.on_activate = on_activate
        self.pty_process: Optional[PtyProcess] = None
        self.output_queue: "queue.Queue[str]" = queue.Queue()
        self.reader_thread: Optional[threading.Thread] = None
        self.after_id: Optional[str] = None
        self.connected = False
        self.current_input = ""
        self.current_directory = os.getcwd()
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

    def reset_screen(self) -> None:
        self.screen = pyte.HistoryScreen(self.columns, self.rows, 4000)
        self.stream = pyte.Stream(self.screen)
        self.render_screen()

    def start_shell(self) -> None:
        self.stop_shell()
        self.reset_screen()
        self.current_input = ""
        self.is_command_line_mode = True
        self.pty_process = PtyProcess.spawn(self.build_shell_args(), dimensions=(self.rows, self.columns))
        self.connected = True
        self.reader_thread = threading.Thread(target=self.reader_loop, daemon=True)
        self.reader_thread.start()
        self.text_widget.focus_set()

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
        self.screen.resize(lines=self.rows, columns=self.columns)
        self.render_screen()

    def on_ctrl_c(self, _event: tk.Event) -> str:
        try:
            selected = self.text_widget.selection_get()
        except Exception:
            selected = ""
        if selected:
            self.clipboard_clear()
            self.clipboard_append(selected)
            return "break"
        self.current_input = ""
        self.is_command_line_mode = False
        self.write_text("\x03")
        return "break"

    def transform_command(self, command_text: str) -> str:
        lines: List[str] = []
        for line in command_text.split("\n"):
            if line.strip() != "cd -":
                lines.append(line)
                continue
            if self.previous_directory:
                escaped = self.previous_directory.replace("'", "''")
                lines.append(f"Set-Location -LiteralPath '{escaped}'")
            else:
                lines.append("Write-Output 'No previous location.'")
        return "\n".join(lines)

    def _render_line_buffer(self, line_buffer: Dict[int, Any]) -> str:
        rendered: List[str] = []
        is_wide = False
        for x in range(self.columns):
            if is_wide:
                is_wide = False
                continue
            char = line_buffer[x].data
            is_wide = wcwidth(char[0]) == 2 if char else False
            rendered.append(char)
        return "".join(rendered).rstrip()

    def render_screen(self) -> None:
        history_lines = [self._render_line_buffer(line) for line in self.screen.history.top]
        visible_lines = [line.rstrip() for line in self.screen.display]

        while visible_lines and visible_lines[-1] == "":
            visible_lines.pop()
        if not visible_lines:
            visible_lines = [""]

        lines = history_lines + visible_lines
        content = "\n".join(lines)

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

        cursor_row = len(history_lines) + getattr(self.screen.cursor, "y", 0) + 1
        cursor_col = getattr(self.screen.cursor, "x", 0)
        self.text_widget.mark_set("insert", f"{max(cursor_row, 1)}.{cursor_col}")
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
        self.stop_shell()
        super().destroy()


class TerminalHost(ctk.CTkFrame):
    def __init__(self, master: ctk.CTkFrame, workspace: "TerminalWorkspace") -> None:
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

        self.terminal = EmbeddedTerminal(self, on_activate=lambda: self.workspace.set_active_host(self))
        self.terminal.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="nsew")

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

    def create_terminal_host(self, parent) -> TerminalHost:
        return TerminalHost(parent, self)

    def mount_root(self, widget: tk.Widget) -> None:
        self.root_widget = widget
        widget.grid(row=0, column=0, sticky="nsew")

    def _insert_into_parent(self, parent: tk.PanedWindow, index: int, widget: tk.Widget) -> None:
        try:
            parent.insert(index, widget)
        except Exception:
            parent.add(widget)

    def replace_widget(self, old_widget: tk.Widget, new_widget: tk.Widget) -> None:
        if old_widget == self.root_widget:
            old_widget.grid_forget()
            self.root_widget = new_widget
            new_widget.grid(row=0, column=0, sticky="nsew")
            return

        parent = old_widget.master
        if isinstance(parent, tk.PanedWindow):
            panes = list(parent.panes())
            index = panes.index(str(old_widget))
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
                    walk(widget.nametowidget(pane_name))
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
        parent = old_host.master

        nested = tk.PanedWindow(
            parent,
            orient=tk.HORIZONTAL if orientation == "horizontal" else tk.VERTICAL,
            sashrelief=tk.RAISED,
            sashwidth=6,
            bd=0,
            bg="#3a4150",
        )

        self.replace_widget(old_host, nested)

        old_host.pack_forget()
        new_host = self.create_terminal_host(nested)

        nested.add(old_host, stretch="always")
        nested.add(new_host, stretch="always")
        self.set_active_host(new_host)

    def close_active(self) -> None:
        if self.active_host is None:
            return
        if len(self.iter_hosts()) == 1:
            self.active_host.terminal.send_command("Clear-Host")
            return

        host = self.active_host
        parent = host.master
        if not isinstance(parent, tk.PanedWindow):
            return

        panes_before = list(parent.panes())
        index = panes_before.index(str(host))
        parent.forget(host)
        host.destroy()

        remaining = list(parent.panes())
        if len(remaining) == 1:
            survivor = parent.nametowidget(remaining[0])
            self.replace_widget(parent, survivor)
            parent.destroy()
            if isinstance(survivor, TerminalHost):
                self.set_active_host(survivor)
            return

        next_index = min(index, len(remaining) - 1)
        next_widget = parent.nametowidget(remaining[next_index])
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
    def __init__(self, app: "QuickCommandApp") -> None:
        super().__init__(app)
        self.app = app
        self.selected_group_id: Optional[str] = None
        self.selected_item_id: Optional[str] = None

        self.title("Quick Command")
        self.geometry("1280x780")
        self.minsize(1040, 640)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.content_frame = ctk.CTkFrame(self, corner_radius=0)
        self.content_frame.grid(row=0, column=0, sticky="nsew")
        self.content_frame.grid_columnconfigure(0, weight=0)
        self.content_frame.grid_columnconfigure(1, weight=0)
        self.content_frame.grid_columnconfigure(2, weight=1)
        self.content_frame.grid_rowconfigure(0, weight=1)

        self.group_panel = ctk.CTkFrame(self.content_frame, width=250)
        self.group_panel.grid(row=0, column=0, padx=(12, 6), pady=12, sticky="nsew")
        self.group_panel.grid_propagate(False)
        self.group_panel.grid_columnconfigure(0, weight=1)
        self.group_panel.grid_rowconfigure(1, weight=1)

        self.item_panel = ctk.CTkFrame(self.content_frame, width=290)
        self.item_panel.grid(row=0, column=1, padx=6, pady=12, sticky="nsew")
        self.item_panel.grid_propagate(False)
        self.item_panel.grid_columnconfigure(0, weight=1)
        self.item_panel.grid_rowconfigure(1, weight=1)

        self.command_panel = ctk.CTkFrame(self.content_frame)
        self.command_panel.grid(row=0, column=2, padx=(6, 12), pady=12, sticky="nsew")
        self.command_panel.grid_columnconfigure(0, weight=1)
        self.command_panel.grid_rowconfigure(1, weight=1)

        self.create_group_panel()
        self.create_item_panel()
        self.create_command_panel()
        self.restore_selection()
        self.refresh_all()

    def create_group_panel(self) -> None:
        header = ctk.CTkFrame(self.group_panel, fg_color="transparent")
        header.grid(row=0, column=0, padx=12, pady=(12, 8), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Groups", font=ctk.CTkFont(size=18, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(header, text="+ New", width=78, command=self.add_group).grid(row=0, column=1, sticky="e")

        self.group_scroll = ctk.CTkScrollableFrame(self.group_panel, corner_radius=10)
        self.group_scroll.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")
        self.group_scroll.grid_columnconfigure(0, weight=1)

    def create_item_panel(self) -> None:
        header = ctk.CTkFrame(self.item_panel, fg_color="transparent")
        header.grid(row=0, column=0, padx=12, pady=(12, 8), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        self.item_title = ctk.CTkLabel(header, text="Items", font=ctk.CTkFont(size=18, weight="bold"))
        self.item_title.grid(row=0, column=0, sticky="w")
        self.add_item_button = ctk.CTkButton(header, text="+ New", width=78, command=self.add_item)
        self.add_item_button.grid(row=0, column=1, sticky="e")

        self.item_scroll = ctk.CTkScrollableFrame(self.item_panel, corner_radius=10)
        self.item_scroll.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")
        self.item_scroll.grid_columnconfigure(0, weight=1)

    def create_command_panel(self) -> None:
        header = ctk.CTkFrame(self.command_panel, fg_color="transparent")
        header.grid(row=0, column=0, padx=14, pady=(14, 8), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.grid(row=0, column=0, sticky="ew")
        title_box.grid_columnconfigure(0, weight=1)

        self.command_title = ctk.CTkLabel(title_box, text="Commands", font=ctk.CTkFont(size=22, weight="bold"), anchor="w")
        self.command_title.grid(row=0, column=0, sticky="w")

        self.command_subtitle = ctk.CTkLabel(title_box, text="Select a group and an item.", anchor="w", text_color=("gray35", "gray70"))
        self.command_subtitle.grid(row=1, column=0, pady=(4, 0), sticky="w")

        action_box = ctk.CTkFrame(header, fg_color="transparent")
        action_box.grid(row=0, column=1, rowspan=2, padx=(12, 0), sticky="e")
        self.add_command_button = ctk.CTkButton(action_box, text="Add Command", width=120, command=self.add_command)
        self.add_command_button.pack(side="left", padx=(0, 8))
        self.run_all_button = ctk.CTkButton(action_box, text="Run All", width=120, command=self.run_all_commands)
        self.run_all_button.pack(side="left")

        self.command_scroll = ctk.CTkScrollableFrame(self.command_panel, corner_radius=10)
        self.command_scroll.grid(row=1, column=0, padx=14, pady=(0, 14), sticky="nsew")
        self.command_scroll.grid_columnconfigure(0, weight=1)

    def restore_selection(self) -> None:
        groups = self.app.data.get("groups", [])
        if not groups:
            self.selected_group_id = None
            self.selected_item_id = None
            return

        if not any(group["id"] == self.selected_group_id for group in groups):
            self.selected_group_id = groups[0]["id"]

        group = self.get_selected_group()
        if not group:
            self.selected_item_id = None
            return

        items = group.get("items", [])
        if not items:
            self.selected_item_id = None
            return

        if not any(item["id"] == self.selected_item_id for item in items):
            self.selected_item_id = items[0]["id"]

    def refresh_all(self) -> None:
        self.restore_selection()
        self.render_groups()
        self.render_items()
        self.render_commands()
        self.add_item_button.configure(state="normal" if self.get_selected_group() else "disabled")
        self.add_command_button.configure(state="normal" if self.get_selected_item() else "disabled")
        self.run_all_button.configure(state="normal" if self.get_selected_item() else "disabled")

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

    def select_group(self, group_id: str) -> None:
        self.selected_group_id = group_id
        group = self.get_selected_group()
        self.selected_item_id = group["items"][0]["id"] if group and group.get("items") else None
        self.refresh_all()

    def select_item(self, item_id: str) -> None:
        group, item = self.find_item_and_parent(item_id)
        if not group or not item:
            return
        self.selected_group_id = group["id"]
        self.selected_item_id = item["id"]
        self.refresh_all()

    def render_groups(self) -> None:
        self.clear_frame(self.group_scroll)
        groups = self.app.data.get("groups", [])
        if not groups:
            ctk.CTkLabel(self.group_scroll, text="No groups yet.", text_color=("gray40", "gray65")).grid(row=0, column=0, padx=12, pady=24, sticky="ew")
            return

        for index, group in enumerate(groups):
            row = ctk.CTkFrame(self.group_scroll, corner_radius=10)
            row.grid(row=index, column=0, padx=6, pady=6, sticky="ew")
            row.grid_columnconfigure(0, weight=1)

            button = ctk.CTkButton(row, text=group["name"], anchor="w", height=38, command=lambda gid=group["id"]: self.select_group(gid))
            if group["id"] == self.selected_group_id:
                button.configure(fg_color=("#1f6aa5", "#144870"))
            else:
                button.configure(fg_color=("gray78", "gray23"), hover_color=("gray72", "gray28"))
            button.grid(row=0, column=0, padx=(8, 6), pady=8, sticky="ew")

            ctk.CTkButton(row, text="Edit", width=54, command=lambda gid=group["id"]: self.rename_group(gid)).grid(row=0, column=1, padx=(0, 6), pady=8)
            ctk.CTkButton(row, text="Del", width=54, fg_color="#c0392b", hover_color="#922b21", command=lambda gid=group["id"]: self.delete_group(gid)).grid(row=0, column=2, padx=(0, 8), pady=8)

    def render_items(self) -> None:
        self.clear_frame(self.item_scroll)
        group = self.get_selected_group()
        self.item_title.configure(text=f"Items - {group['name']}" if group else "Items")
        if not group:
            ctk.CTkLabel(self.item_scroll, text="Select a group first.", text_color=("gray40", "gray65")).grid(row=0, column=0, padx=12, pady=24, sticky="ew")
            return

        items = group.get("items", [])
        if not items:
            ctk.CTkLabel(self.item_scroll, text="No items in this group.", text_color=("gray40", "gray65")).grid(row=0, column=0, padx=12, pady=24, sticky="ew")
            return

        for index, item in enumerate(items):
            row = ctk.CTkFrame(self.item_scroll, corner_radius=10)
            row.grid(row=index, column=0, padx=6, pady=6, sticky="ew")
            row.grid_columnconfigure(0, weight=1)
            button = ctk.CTkButton(row, text=item["name"], anchor="w", height=38, command=lambda iid=item["id"]: self.select_item(iid))
            if item["id"] == self.selected_item_id:
                button.configure(fg_color=("#1f6aa5", "#144870"))
            else:
                button.configure(fg_color=("gray78", "gray23"), hover_color=("gray72", "gray28"))
            button.grid(row=0, column=0, padx=(8, 6), pady=8, sticky="ew")
            ctk.CTkButton(row, text="Edit", width=54, command=lambda iid=item["id"]: self.rename_item(iid)).grid(row=0, column=1, padx=(0, 6), pady=8)
            ctk.CTkButton(row, text="Del", width=54, fg_color="#c0392b", hover_color="#922b21", command=lambda iid=item["id"]: self.delete_item(iid)).grid(row=0, column=2, padx=(0, 8), pady=8)

    def render_commands(self) -> None:
        self.clear_frame(self.command_scroll)
        group = self.get_selected_group()
        item = self.get_selected_item()
        if not group or not item:
            self.command_title.configure(text="Commands")
            self.command_subtitle.configure(text="Select a group and an item.")
            ctk.CTkLabel(self.command_scroll, text="The selected item's commands will appear here.", text_color=("gray40", "gray65")).grid(row=0, column=0, padx=16, pady=32, sticky="ew")
            return

        commands = item.get("commands", [])
        self.command_title.configure(text=item["name"])
        self.command_subtitle.configure(text=f"Group: {group['name']} | Commands: {len(commands)}")
        if not commands:
            ctk.CTkLabel(self.command_scroll, text="No commands yet.", text_color=("gray40", "gray65")).grid(row=0, column=0, padx=16, pady=32, sticky="ew")
            return

        for index, command in enumerate(commands, start=1):
            card = ctk.CTkFrame(self.command_scroll, corner_radius=12)
            card.grid(row=index - 1, column=0, padx=8, pady=8, sticky="ew")
            card.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(card, text=f"Command {index}", font=ctk.CTkFont(size=15, weight="bold"), anchor="w").grid(row=0, column=0, padx=14, pady=(12, 8), sticky="ew")
            preview = ctk.CTkTextbox(card, height=96, wrap="word")
            preview.grid(row=1, column=0, padx=14, pady=(0, 10), sticky="ew")
            preview.insert("1.0", command["command"])
            preview.configure(state="disabled")
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.grid(row=2, column=0, padx=14, pady=(0, 12), sticky="e")
            ctk.CTkButton(row, text="Edit", width=78, command=lambda cid=command["id"]: self.edit_command(cid)).pack(side="left", padx=(0, 8))
            ctk.CTkButton(row, text="Copy", width=78, command=lambda text=command["command"]: self.copy_command(text)).pack(side="left", padx=(0, 8))
            ctk.CTkButton(row, text="Run", width=78, command=lambda text=command["command"], label=f"{item['name']} / Command {index}": self.app.send_to_active_terminal(text, label)).pack(side="left", padx=(0, 8))
            ctk.CTkButton(row, text="Delete", width=78, fg_color="#c0392b", hover_color="#922b21", command=lambda cid=command["id"]: self.delete_command(cid)).pack(side="left")

    def add_group(self) -> None:
        name = SingleLineDialog.ask(self, "New Group", "Enter group name:")
        if not name:
            return
        new_group = {"id": uuid.uuid4().hex, "name": name, "items": []}
        self.app.data["groups"].append(new_group)
        self.selected_group_id = new_group["id"]
        self.selected_item_id = None
        self.app.save_data()
        self.refresh_all()
        self.app.append_status(f"Created group: {name}")

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
        self.app.save_data()
        self.refresh_all()
        self.app.append_status(f"Deleted group: {target['name']}")

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
        self.app.save_data()
        self.refresh_all()
        self.app.append_status(f"Created item '{name}' in group '{group['name']}'")

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
        self.app.save_data()
        self.refresh_all()
        self.app.append_status(f"Deleted item: {item['name']}")

    def add_command(self) -> None:
        item = self.get_selected_item()
        if not item:
            messagebox.showwarning("Warning", "Please select an item first.", parent=self)
            return
        command_text = CommandDialog.ask(self, "Add Command")
        if not command_text:
            return
        item["commands"].append({"id": uuid.uuid4().hex, "command": command_text})
        self.app.save_data()
        self.refresh_all()
        self.app.append_status(f"Added command to item '{item['name']}'")

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
        self.app.save_data()
        self.refresh_all()
        self.app.append_status(f"Deleted command: {command['command'].splitlines()[0][:60]}")

    def copy_command(self, command_text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(command_text)
        self.app.append_status("Command copied to clipboard.")

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
        self.grid_rowconfigure(2, weight=0)

        self.create_toolbar()
        self.create_workspace()
        self.create_status_log()
        self.create_initial_tab()
        self.after(200, self.prime_quick_command_window)

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

    def create_status_log(self) -> None:
        self.status_frame = ctk.CTkFrame(self, height=150)
        self.status_frame.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="ew")
        self.status_frame.grid_columnconfigure(0, weight=1)
        self.status_frame.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self.status_frame, fg_color="transparent")
        header.grid(row=0, column=0, padx=12, pady=(12, 6), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Status Log", font=ctk.CTkFont(size=15, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(header, text="Clear", width=80, command=self.clear_status_log).grid(row=0, column=1, sticky="e")

        self.status_log = ctk.CTkTextbox(self.status_frame, height=110, wrap="word")
        self.status_log.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")
        self.status_log.configure(state="disabled")

    def create_initial_tab(self) -> None:
        self.add_tab()

    def prime_quick_command_window(self) -> None:
        if self.quick_command_window is not None and self.quick_command_window.winfo_exists():
            return
        try:
            self.quick_command_window = QuickCommandWindow(self)
            self.quick_command_window.withdraw()
        except Exception as error:
            self.quick_command_window = None
            self.append_status(f"Quick Command preload failed: {error}")

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

    def append_status(self, message: str) -> None:
        self.status_log.configure(state="normal")
        self.status_log.insert("end", message + "\n")
        self.status_log.see("end")
        self.status_log.configure(state="disabled")

    def clear_status_log(self) -> None:
        self.status_log.configure(state="normal")
        self.status_log.delete("1.0", "end")
        self.status_log.configure(state="disabled")


if __name__ == "__main__":
    app = QuickCommandApp()
    app.mainloop()
