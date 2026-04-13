import os
import queue
import re
import shlex
import subprocess
import threading
import tkinter as tk
import tkinter.font as tkfont
from typing import Any, Dict, List, Optional

import pyte
from pyte.screens import wcwidth
from winpty import PtyProcess

from theme.bootstrap import ctk, write_startup_log
from theme.styles import TERMINAL_COLORS

write_startup_log("module import: pyte ready")
write_startup_log("module import: winpty ready")


class EmbeddedTerminal(ctk.CTkFrame):
    def __init__(self, master: ctk.CTkFrame, on_activate, initial_cwd: Optional[str] = None, on_state_change=None) -> None:
        super().__init__(master, corner_radius=10, fg_color=("#f4f6f8", "#11161e"))
        self.on_activate = on_activate
        self.on_state_change = on_state_change
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
        self.rendered_line_lengths: List[int] = [0]
        self.selection_anchor: Optional[str] = None
        self.context_menu_provider = None
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
            bg=TERMINAL_COLORS["background"],
            fg=TERMINAL_COLORS["foreground"],
            insertbackground=TERMINAL_COLORS["foreground"],
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
        self.configure_text_tags()

        self.y_scroll = ctk.CTkScrollbar(self, orientation="vertical", command=self.text_widget.yview)
        self.y_scroll.grid(row=0, column=1, sticky="ns")
        self.x_scroll = ctk.CTkScrollbar(self, orientation="horizontal", command=self.text_widget.xview)
        self.x_scroll.grid(row=1, column=0, sticky="ew")
        self.text_widget.configure(yscrollcommand=self.y_scroll.set, xscrollcommand=self.x_scroll.set)

        self.text_widget.bind("<Button-1>", self.on_click)
        self.text_widget.bind("<B1-Motion>", self.on_drag_select)
        self.text_widget.bind("<ButtonRelease-1>", self.on_release_select)
        self.text_widget.bind("<FocusIn>", self.on_focus)
        self.text_widget.bind("<Configure>", self.on_resize)
        self.text_widget.bind("<KeyPress>", self.on_key_press)
        self.text_widget.bind("<Control-v>", self.on_paste)
        self.text_widget.bind("<Control-V>", self.on_paste)
        self.text_widget.bind("<Control-c>", self.on_ctrl_c)
        self.text_widget.bind("<Control-C>", self.on_ctrl_c)
        self.text_widget.bind("<Button-3>", self.show_context_menu)

        self.reset_screen()
        self.start_shell()
        self.schedule_output_pump()

    def configure_text_tags(self) -> None:
        for name, color in {
            "prompt": TERMINAL_COLORS["prompt"],
            "added": TERMINAL_COLORS["added"],
            "deleted": TERMINAL_COLORS["deleted"],
            "modified": TERMINAL_COLORS["modified"],
            "warning": TERMINAL_COLORS["warning"],
            "error": TERMINAL_COLORS["error"],
            "muted": TERMINAL_COLORS["muted"],
        }.items():
            self.text_widget.tag_configure(name, foreground=color)

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
        self.pty_process = PtyProcess.spawn(self.build_shell_args(), cwd=self.current_directory, env=self.build_shell_env(), dimensions=(self.rows, self.columns))
        self.connected = True
        self.notify_state_change()
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
        self.notify_state_change()

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
        prefix, token, command_name = self.split_completion_context(current_input)
        if not token:
            return current_input
        local_completion = self.complete_local_token(token, command_name)
        if local_completion is not None and local_completion != token:
            return prefix + local_completion
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
            "foreach ($match in $matches) { while (-not $match.StartsWith($prefix)) { $prefix = $prefix.Substring(0, $prefix.Length - 1); if ($prefix.Length -eq 0) { break } } } "
            "if ($prefix.Length -gt $line.Length) { $prefix } else { $matches[0] }"
        )
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        startup_info = None
        if os.name == "nt":
            startup_info = subprocess.STARTUPINFO()
            startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup_info.wShowWindow = 0
        try:
            result = subprocess.run([shell_path, "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3, creationflags=creation_flags, startupinfo=startup_info)
        except Exception:
            return current_input
        completed = result.stdout.strip()
        if not completed:
            return current_input
        normalized = self.normalize_completion(token, completed, command_name)
        if normalized == token:
            return current_input
        return prefix + normalized

    def is_path_completion_context(self, token: str, command_name: str) -> bool:
        if not token:
            return False
        if command_name.lower() in ("cd", "chdir", "sl", "set-location", "vim"):
            return True
        return any(sep in token for sep in ("\\", "/")) or token.startswith((".", "~"))

    def complete_local_token(self, token: str, command_name: str) -> Optional[str]:
        if not self.is_path_completion_context(token, command_name):
            return None
        raw_token = self.strip_wrapping_quotes(token)
        if not raw_token:
            return None

        leading_prefix = ""
        lookup_token = raw_token
        if lookup_token.startswith((".\\", "./")):
            leading_prefix = lookup_token[:2]
            lookup_token = lookup_token[2:]

        lookup_token = lookup_token.replace("/", os.sep).replace("\\", os.sep)
        if lookup_token.endswith(os.sep):
            search_dir_token = lookup_token.rstrip(os.sep)
            partial_name = ""
        else:
            search_dir_token, partial_name = os.path.split(lookup_token)

        if search_dir_token:
            if os.path.isabs(search_dir_token):
                search_dir = os.path.normpath(search_dir_token)
            else:
                search_dir = os.path.normpath(os.path.join(self.current_directory, search_dir_token))
        else:
            search_dir = self.current_directory

        if not os.path.isdir(search_dir):
            return None

        try:
            entries = list(os.scandir(search_dir))
        except OSError:
            return None

        partial_lower = partial_name.lower()
        matches = []
        for entry in entries:
            if partial_lower and not entry.name.lower().startswith(partial_lower):
                continue
            matches.append(entry)

        if not matches:
            return None

        matches.sort(key=lambda entry: (not entry.is_dir(), entry.name.lower()))
        chosen = matches[0].name
        if search_dir_token:
            completed_token = os.path.normpath(os.path.join(search_dir_token, chosen))
        else:
            completed_token = chosen
        if leading_prefix:
            completed_token = leading_prefix + completed_token
        return completed_token

    def split_completion_context(self, current_input: str) -> tuple[str, str, str]:
        in_quote: Optional[str] = None
        last_boundary = 0
        first_boundary: Optional[int] = None
        for index, char in enumerate(current_input):
            if char in ("'", '"'):
                if in_quote is None:
                    in_quote = char
                elif in_quote == char:
                    in_quote = None
            elif char.isspace() and in_quote is None:
                if first_boundary is None:
                    first_boundary = index
                last_boundary = index + 1
        prefix = current_input[:last_boundary]
        token = current_input[last_boundary:]
        command_name = current_input[:first_boundary].strip() if first_boundary is not None else current_input.strip()
        if " " in command_name or "\t" in command_name:
            command_name = command_name.split()[0]
        return prefix, token, command_name

    def normalize_completion(self, original_token: str, completed_input: str, command_name: str) -> str:
        normalized_completed = self.strip_wrapping_quotes(completed_input.strip())
        if not normalized_completed:
            return original_token
        command = command_name.lower()
        if command in ("cd", "chdir", "sl", "set-location", "vim"):
            normalized_completed = normalized_completed.replace("/", os.sep).replace("\\", os.sep)
            if normalized_completed.startswith((".\\", "./")):
                normalized_completed = normalized_completed[2:]
            if command == "vim" and original_token.lower() == "vim" and not normalized_completed:
                return original_token
            if os.sep in normalized_completed:
                normalized_completed = os.path.basename(normalized_completed)
        return normalized_completed

    def sync_current_input(self, new_input: str) -> None:
        self.erase_current_input_from_terminal()
        if new_input:
            self.write_text(new_input)
        self.current_input = new_input

    def can_accept_input(self) -> bool:
        return self.connected and self.pty_process is not None and self.is_command_line_mode

    def insert_into_prompt(self, text: str) -> bool:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        if not normalized or not self.can_accept_input():
            return False
        next_input = f"{self.current_input}{normalized}" if self.current_input else normalized
        self.current_input = next_input
        self.sync_current_input(next_input)
        self.text_widget.focus_set()
        return True

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
        compat_command = self.parse_compat_command(normalized)
        if compat_command is not None:
            self.execute_compat_command(compat_command, from_prompt=False)
            return
        payload = self.transform_command(normalized).replace("\n", "\r") + "\r"
        self.current_input = ""
        self.is_command_line_mode = False
        self.write_text(payload)
        self.text_widget.focus_set()

    def set_active(self, active: bool) -> None:
        self.configure(border_width=0, border_color="#11161e")

    def on_click(self, _event: tk.Event) -> str:
        self.on_activate()
        self.text_widget.focus_set()
        self.clear_selection()
        return "break"

    def clear_selection(self) -> None:
        try:
            self.text_widget.tag_remove("sel", "1.0", "end")
        except Exception:
            pass
        self.selection_anchor = None

    def clamp_index_to_text(self, index: str, allow_line_end_clamp: bool = False) -> Optional[str]:
        try:
            line_number, column = self.text_widget.index(index).split(".")
            row = max(int(line_number), 1)
            col = max(int(column), 0)
        except Exception:
            return None
        if row > len(self.rendered_line_lengths):
            return None
        line_length = self.rendered_line_lengths[row - 1]
        if line_length <= 0:
            return None
        if col >= line_length:
            if not allow_line_end_clamp:
                return None
            col = line_length - 1
        return f"{row}.{col}"

    def on_drag_select(self, event: tk.Event) -> str:
        self.on_activate()
        self.text_widget.focus_set()
        index = self.clamp_index_to_text(f"@{event.x},{event.y}", allow_line_end_clamp=True)
        if index is None:
            if self.selection_anchor is None:
                self.clear_selection()
            return "break"
        if self.selection_anchor is None:
            self.selection_anchor = index
        start = self.selection_anchor
        end = index
        try:
            if self.text_widget.compare(start, ">", end):
                start, end = end, start
            self.text_widget.tag_remove("sel", "1.0", "end")
            self.text_widget.tag_add("sel", start, f"{end}+1c")
        except Exception:
            self.clear_selection()
        return "break"

    def on_release_select(self, _event: tk.Event) -> str:
        if self.selection_anchor is None:
            self.clear_selection()
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
        context_menu = tk.Menu(self, tearoff=0)
        try:
            has_selection = bool(self.text_widget.tag_ranges("sel"))
        except Exception:
            has_selection = False
        context_menu.add_command(label="Copy", command=self.copy_selection, state="normal" if has_selection else "disabled")
        context_menu.add_command(label="Paste", command=lambda: self.on_paste(None))
        context_menu.add_command(label="Interrupt", command=lambda: self.on_ctrl_c(None))
        if self.context_menu_provider is not None:
            self.context_menu_provider(context_menu)
        try:
            context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            context_menu.grab_release()
        return "break"

    def set_context_menu_provider(self, provider) -> None:
        self.context_menu_provider = provider

    def notify_state_change(self) -> None:
        if self.on_state_change is not None:
            try:
                self.on_state_change()
            except Exception:
                pass

    def transform_command(self, command_text: str) -> str:
        lines: List[str] = []
        for line in command_text.split("\n"):
            stripped = line.strip()
            if stripped:
                mapped = self.map_linux_compat_command(line)
                if mapped is not None:
                    lines.append(mapped)
                    continue
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

    def map_linux_compat_command(self, line: str) -> Optional[str]:
        stripped = line.strip()
        if not stripped:
            return None
        find_command = self.map_find_command(stripped)
        if find_command is not None:
            return find_command
        return None

    def parse_command_tokens(self, command: str) -> Optional[List[str]]:
        try:
            return shlex.split(command, posix=False)
        except ValueError:
            return None

    def strip_wrapping_quotes(self, value: str) -> str:
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            return value[1:-1]
        return value

    def to_powershell_single_quoted(self, value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    def normalize_target_path(self, raw_path: str) -> str:
        cleaned = self.strip_wrapping_quotes(raw_path)
        expanded = os.path.expandvars(os.path.expanduser(cleaned))
        if os.path.isabs(expanded):
            return os.path.normpath(expanded)
        return os.path.normpath(os.path.join(self.current_directory, expanded))

    def map_vim_command(self, stripped_command: str) -> Optional[str]:
        tokens = self.parse_command_tokens(stripped_command)
        if not tokens or tokens[0].lower() != "vim":
            return None
        if len(tokens) == 1:
            return "notepad.exe"
        target_path = self.normalize_target_path(tokens[1])
        quoted_target = self.to_powershell_single_quoted(target_path)
        return (
            f"$qcTarget = {quoted_target}; "
            "if (-not (Test-Path -LiteralPath $qcTarget)) { "
            "New-Item -ItemType File -Path $qcTarget -Force | Out-Null }; "
            "Start-Process -FilePath notepad.exe -ArgumentList @($qcTarget)"
        )

    def parse_compat_command(self, raw_command: str) -> Optional[Dict[str, Optional[str]]]:
        tokens = self.parse_command_tokens(raw_command.strip())
        if not tokens:
            return None
        if tokens[0].lower() != "vim":
            return None
        if len(tokens) == 1:
            return {"kind": "vim", "target_path": None}
        return {"kind": "vim", "target_path": self.normalize_target_path(tokens[1])}

    def execute_compat_command(self, compat_command: Dict[str, Optional[str]], from_prompt: bool) -> None:
        kind = compat_command.get("kind")
        if kind != "vim":
            return

        raw_user_input = self.current_input if from_prompt else ""
        self.current_input = ""
        if from_prompt:
            self.is_command_line_mode = False
            if self.pty_process is not None:
                try:
                    self.pty_process.sendintr()
                except Exception:
                    pass
            self.write_text("\x03")

        target_path = compat_command.get("target_path")
        if target_path:
            target_directory = os.path.dirname(target_path)
            if target_directory and not os.path.exists(target_directory):
                os.makedirs(target_directory, exist_ok=True)
            if not os.path.exists(target_path):
                with open(target_path, "a", encoding="utf-8"):
                    pass
            subprocess.Popen(["notepad.exe", target_path], cwd=self.current_directory)
        else:
            subprocess.Popen(["notepad.exe"], cwd=self.current_directory)

        if from_prompt and raw_user_input:
            write_startup_log(f"compat vim intercepted: {raw_user_input}")
        self.text_widget.focus_set()

    def map_find_command(self, stripped_command: str) -> Optional[str]:
        tokens = self.parse_command_tokens(stripped_command)
        if not tokens or tokens[0].lower() != "find" or len(tokens) < 4:
            return None
        search_path = tokens[1]
        pattern: Optional[str] = None
        name_mode: Optional[str] = None
        type_filter: Optional[str] = None
        index = 2
        while index < len(tokens):
            token = tokens[index].lower()
            if token in ("-name", "-iname") and index + 1 < len(tokens):
                name_mode = token
                pattern = self.strip_wrapping_quotes(tokens[index + 1])
                index += 2
                continue
            if token == "-type" and index + 1 < len(tokens):
                type_filter = self.strip_wrapping_quotes(tokens[index + 1]).lower()
                index += 2
                continue
            return None
        if pattern is None:
            return None

        literal_path = self.normalize_target_path(search_path)
        path_literal = self.to_powershell_single_quoted(literal_path)
        pattern_literal = self.to_powershell_single_quoted(pattern)
        operator = "-like" if name_mode == "-iname" else "-clike"
        clauses: List[str] = [f"$_.Name {operator} {pattern_literal}"]
        if type_filter == "f":
            clauses.append("-not $_.PSIsContainer")
        elif type_filter == "d":
            clauses.append("$_.PSIsContainer")
        filter_clause = " -and ".join(clauses)
        return (
            f"$qcFindPath = {path_literal}; "
            "if (-not (Test-Path -LiteralPath $qcFindPath)) { "
            "Write-Error ('find: path not found: ' + $qcFindPath) } "
            "else { "
            f"Get-ChildItem -LiteralPath $qcFindPath -Recurse -Force -ErrorAction SilentlyContinue | "
            f"Where-Object {{ {filter_clause} }} | "
            "ForEach-Object { $_.FullName } }"
        )

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

    def semantic_tags_for_line(self, line: str) -> List[str]:
        tags: List[str] = []
        stripped = line.strip()
        lower = stripped.lower()
        if not stripped:
            return tags
        if line.startswith("PS ") or stripped.startswith("PS "):
            tags.append("prompt")
            return tags
        if stripped.startswith("[terminal disconnected]"):
            tags.append("muted")
            return tags

        if re.match(r"^(fatal:|error:|failed\b|exception\b|traceback\b)", lower):
            tags.append("error")
            return tags
        if re.match(r"^(warning:|warn\b)", lower):
            tags.append("warning")
            return tags

        git_status_prefixes = (
            "changes to be committed:",
            "changes not staged for commit:",
            "untracked files:",
            "nothing added to commit",
            "nothing to commit",
            "your branch is",
            "on branch ",
        )
        if lower.startswith(git_status_prefixes):
            if lower.startswith("untracked files:"):
                tags.append("warning")
            elif lower.startswith("nothing to commit") or lower.startswith("your branch is") or lower.startswith("on branch "):
                tags.append("muted")
            else:
                tags.append("muted")
            return tags

        if re.match(r"^\s*modified:\s+", lower):
            tags.append("modified")
            return tags
        if re.match(r"^\s*deleted:\s+", lower):
            tags.append("deleted")
            return tags
        if re.match(r"^\s*(new file|added|created):\s+", lower):
            tags.append("added")
            return tags
        if re.match(r"^\s*renamed:\s+", lower):
            tags.append("modified")
            return tags
        if re.match(r"^\s*\?\?\s+", stripped):
            tags.append("warning")
            return tags
        if re.match(r"^\s*[amr][md]?\s+", lower):
            if "d" in lower[:4]:
                tags.append("deleted")
            elif "a" in lower[:4]:
                tags.append("added")
            else:
                tags.append("modified")
            return tags

        if re.search(r"\b(warning|deprecated)\b", lower):
            tags.append("warning")
            return tags
        if re.search(r"\b(failed|failure|fatal|error)\b", lower):
            tags.append("error")
            return tags
        return tags

    def render_screen(self) -> None:
        history_lines = [self._render_line_buffer(line) for line in self.screen.history.top]
        cursor_row = getattr(self.screen.cursor, "y", 0)
        cursor_col = getattr(self.screen.cursor, "x", 0)
        visible_lines = [self._render_display_line(line, row == cursor_row, cursor_col) for row, line in enumerate(self.screen.display)]
        lines = history_lines + visible_lines
        self.rendered_line_lengths = [len(line) for line in lines] if lines else [0]
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
        self.notify_state_change()

        self.text_widget.delete("1.0", "end")
        for index, line in enumerate(lines, start=1):
            self.text_widget.insert("end", line, tuple(self.semantic_tags_for_line(line)))
            if index < len(lines):
                self.text_widget.insert("end", "\n")

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
            payload, _ = key_map[event.keysym]
            if event.keysym == "BackSpace" and self.is_command_line_mode and self.current_input:
                self.current_input = self.current_input[:-1]
            elif event.keysym == "Return":
                raw_user_input = self.current_input
                compat_command = self.parse_compat_command(raw_user_input)
                if compat_command is not None:
                    self.execute_compat_command(compat_command, from_prompt=True)
                    return "break"
                final_execution_command = self.transform_command(raw_user_input)
                self.current_input = ""
                self.is_command_line_mode = False
                if final_execution_command != raw_user_input:
                    payload = final_execution_command.replace("\n", "\r") + "\r"
            elif event.keysym == "Tab" and self.is_command_line_mode:
                completed = self.complete_input(self.current_input)
                if completed != self.current_input:
                    self.sync_current_input(completed)
                return "break"
            elif event.keysym == "Escape":
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
        for attr in ["after_id", "interrupt_after_id", "resize_after_id"]:
            token = getattr(self, attr)
            if token is not None:
                try:
                    self.after_cancel(token)
                except Exception:
                    pass
        self.stop_shell()
        super().destroy()
