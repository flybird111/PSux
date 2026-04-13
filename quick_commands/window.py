import uuid
import tkinter as tk
from tkinter import messagebox
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from theme.bootstrap import ctk
from theme.styles import QUICK_COMMAND_TOKENS as TOKENS
from ui.dialogs import CommandDialog, SingleLineDialog

if TYPE_CHECKING:
    from main import QuickCommandApp


class QuickCommandWindow(ctk.CTkToplevel):
    def __init__(self, app: "QuickCommandApp") -> None:
        super().__init__(app)
        self.app = app
        self.selected_group_id: Optional[str] = None
        self.selected_item_id: Optional[str] = None
        self.selected_command_id: Optional[str] = None
        self.preview_selected_line_number: Optional[int] = None
        self.preview_line_map: Dict[int, Dict[str, Any]] = {}
        self.preview_command_ranges: Dict[str, Tuple[str, str]] = {}
        self.preview_selected_line_text: Optional[str] = None
        self.preview_menu = tk.Menu(self, tearoff=0)

        self.title("Quick Command")
        self.geometry("1180x720")
        self.minsize(980, 620)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.configure(fg_color=TOKENS["bg"])

        self.group_menu = tk.Menu(self, tearoff=0)
        self.item_menu = tk.Menu(self, tearoff=0)
        self.command_menu = tk.Menu(self, tearoff=0)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.shell = ctk.CTkFrame(self, fg_color=TOKENS["bg"], corner_radius=0)
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

    def create_header(self) -> None:
        header = ctk.CTkFrame(self.shell, fg_color=TOKENS["panel_alt"], corner_radius=0, height=32)
        header.grid(row=0, column=0, columnspan=3, sticky="ew")
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(header, text="QUICK COMMAND", text_color=TOKENS["text_dim"], font=ctk.CTkFont(size=11, weight="bold")).grid(row=0, column=0, padx=(10, 8), pady=5, sticky="w")
        ctk.CTkLabel(header, text="Explorer / List / Preview", text_color=TOKENS["selected_text"], font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=1, pady=5, sticky="w")
        toolbar = ctk.CTkFrame(header, fg_color=TOKENS["panel_alt"])
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
        title_wrap = ctk.CTkFrame(self.command_panel, fg_color=TOKENS["panel_alt"])
        title_wrap.grid(row=0, column=0, padx=10, pady=(8, 3), sticky="ew")
        title_wrap.grid_columnconfigure(0, weight=1)
        self.command_title = ctk.CTkLabel(title_wrap, text="No Selection", text_color=TOKENS["text"], font=ctk.CTkFont(size=15, weight="bold"), anchor="w")
        self.command_title.grid(row=0, column=0, sticky="w")
        self.command_subtitle = ctk.CTkLabel(title_wrap, text="Choose a group and item to inspect commands.", text_color=TOKENS["text_dim"], font=ctk.CTkFont(size=10), anchor="w")
        self.command_subtitle.grid(row=1, column=0, pady=(2, 0), sticky="w")
        actions = ctk.CTkFrame(title_wrap, fg_color=TOKENS["panel_alt"])
        actions.grid(row=0, column=1, rowspan=2, sticky="e")
        self.command_new_button = self.make_action_button(actions, "New Cmd", self.add_command)
        self.command_new_button.pack(side="left", padx=(0, 6))
        self.command_run_all_button = self.make_action_button(actions, "Run All", self.run_all_commands)
        self.command_run_all_button.pack(side="left")
        list_header = ctk.CTkFrame(self.command_panel, fg_color=TOKENS["panel_alt"])
        list_header.grid(row=1, column=0, padx=10, pady=(0, 3), sticky="ew")
        ctk.CTkLabel(list_header, text="COMMANDS", text_color=TOKENS["text_dim"], font=ctk.CTkFont(size=10, weight="bold")).pack(side="left")
        self.command_scroll = ctk.CTkScrollableFrame(self.command_panel, fg_color=TOKENS["panel"], corner_radius=0)
        self.command_scroll.grid(row=2, column=0, padx=8, pady=(0, 4), sticky="nsew")
        self.command_scroll.grid_columnconfigure(0, weight=1)
        preview_header = ctk.CTkFrame(self.command_panel, fg_color=TOKENS["panel_alt"])
        preview_header.grid(row=3, column=0, padx=10, pady=(0, 3), sticky="ew")
        ctk.CTkLabel(preview_header, text="PREVIEW", text_color=TOKENS["text_dim"], font=ctk.CTkFont(size=10, weight="bold")).pack(side="left")
        preview_shell = ctk.CTkFrame(self.command_panel, fg_color=TOKENS["code_bg"], corner_radius=8)
        preview_shell.grid(row=4, column=0, padx=8, pady=(0, 6), sticky="nsew")
        preview_shell.grid_columnconfigure(0, weight=1)
        preview_shell.grid_rowconfigure(0, weight=1)
        self.command_preview = tk.Text(preview_shell, wrap="none", bg=TOKENS["code_bg"], fg=TOKENS["selected_text"], relief="flat", bd=0, padx=10, pady=10, font=("Consolas", 11), insertbackground=TOKENS["selected_text"])
        self.command_preview.grid(row=0, column=0, sticky="nsew")
        self.command_preview.configure(state="normal", exportselection=False, cursor="arrow")
        self.command_preview.tag_configure("command_block_highlight", background=TOKENS["line_selected"])
        self.command_preview.bind("<Button-3>", self.on_preview_right_click)
        self.command_preview.bind("<Button-1>", self.on_preview_click)
        self.command_preview.bind("<FocusIn>", lambda _event: self.command_preview.configure(cursor="xterm"))
        self.command_preview.bind("<Key>", lambda _event: "break")
        self.command_preview.bind("<Control-v>", lambda _event: "break")
        self.command_preview.bind("<Control-V>", lambda _event: "break")
        self.command_preview.bind("<Control-c>", self.on_preview_copy_shortcut)
        self.command_preview.bind("<Control-C>", self.on_preview_copy_shortcut)
        self.command_preview.bind("<Control-a>", self.on_preview_select_all_shortcut)
        self.command_preview.bind("<Control-A>", self.on_preview_select_all_shortcut)
        self.preview_menu.add_command(label="Copy", command=self.copy_preview_selection)
        self.preview_menu.add_command(label="Select All", command=self.select_all_preview)

    def make_panel(self, parent, width: int) -> ctk.CTkFrame:
        panel = ctk.CTkFrame(parent, fg_color=TOKENS["panel"], corner_radius=8, border_width=1, border_color=TOKENS["border"], width=width)
        if width:
            panel.grid_propagate(False)
        return panel

    def make_scroll(self, parent) -> ctk.CTkScrollableFrame:
        scroll = ctk.CTkScrollableFrame(parent, fg_color=TOKENS["panel"], corner_radius=0)
        scroll.grid(row=1, column=0, padx=5, pady=(0, 3), sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)
        return scroll

    def make_section_header(self, parent, title: str, action: Tuple[str, Any]) -> ctk.CTkLabel:
        header = ctk.CTkFrame(parent, fg_color=TOKENS["panel_alt"])
        header.grid(row=0, column=0, padx=8, pady=(8, 2), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        label = ctk.CTkLabel(header, text=title, text_color=TOKENS["text_dim"], font=ctk.CTkFont(size=10, weight="bold"))
        label.grid(row=0, column=0, sticky="w")
        self.make_action_button(header, action[0], action[1]).grid(row=0, column=1, sticky="e")
        return label

    def make_action_button(self, parent, text: str, command) -> ctk.CTkButton:
        return ctk.CTkButton(parent, text=text, command=command, height=20, width=50, corner_radius=4, fg_color=TOKENS["panel_soft"], hover_color=TOKENS["hover"], text_color=TOKENS["selected_text"], border_width=0, font=ctk.CTkFont(size=10, weight="bold"))

    def configure_menus(self) -> None:
        self.group_menu.add_command(label="Rename Group", command=self.rename_selected_group)
        self.group_menu.add_command(label="Delete Group", command=self.delete_selected_group)
        self.item_menu.add_command(label="Rename Item", command=self.rename_selected_item)
        self.item_menu.add_command(label="Delete Item", command=self.delete_selected_item)
        self.command_menu.add_command(label="Insert", command=self.insert_selected_command)
        self.command_menu.add_command(label="Run", command=self.run_selected_command)
        self.command_menu.add_command(label="Copy", command=self.copy_selected_command)
        self.command_menu.add_command(label="Edit", command=self.edit_selected_command)
        self.command_menu.add_separator()
        self.command_menu.add_command(label="Delete", command=self.delete_selected_command)

    def split_command_text(self, command_text: str) -> List[str]:
        commands: List[str] = []
        for raw_line in command_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            commands.append(stripped)
        return commands

    def command_preview_text(self, command_text: str) -> str:
        lines: List[str] = []
        for raw_line in command_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            lines.append(raw_line.rstrip())
        return "\n".join(lines)

    def summarize_command(self, command_text: str, index: int) -> Tuple[str, str]:
        lines = command_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        description: Optional[str] = None
        command_line: Optional[str] = None

        for raw_line in lines:
            stripped = raw_line.strip()
            if not stripped:
                continue
            if stripped.startswith("#") and description is None:
                description = stripped.lstrip("#").strip()
                continue
            command_line = stripped
            break

        if command_line is None:
            command_line = ""
        if description:
            left = f"#{index} {description}".strip()
        else:
            left = f"#{index}"
        return left, command_line

    def insert_command_texts(self, item: Dict[str, Any], command_text: str, insert_index: Optional[int] = None) -> List[Dict[str, Any]]:
        commands = self.split_command_text(command_text)
        if not commands:
            return []
        new_commands = [{"id": uuid.uuid4().hex, "command": command} for command in commands]
        target_index = len(item.get("commands", [])) if insert_index is None else max(0, min(insert_index, len(item.get("commands", []))))
        item.setdefault("commands", [])
        for offset, command in enumerate(new_commands):
            item["commands"].insert(target_index + offset, command)
        return new_commands

    def replace_command_text(self, item: Dict[str, Any], command_id: str, command_text: str) -> List[Dict[str, Any]]:
        commands = self.split_command_text(command_text)
        if not commands:
            return []
        existing_index = next((index for index, entry in enumerate(item.get("commands", [])) if entry["id"] == command_id), None)
        if existing_index is None:
            return []
        new_commands = [{"id": uuid.uuid4().hex, "command": command} for command in commands]
        item["commands"].pop(existing_index)
        for offset, command in enumerate(new_commands):
            item["commands"].insert(existing_index + offset, command)
        return new_commands

    def restore_selection(self) -> None:
        groups = self.app.data.get("groups", [])
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
        self.header_new_item.configure(state="normal" if has_group else "disabled")
        self.header_new_command.configure(state="normal" if has_item else "disabled")
        self.header_run_all.configure(state="normal" if has_item else "disabled")
        self.command_new_button.configure(state="normal" if has_item else "disabled")
        self.command_run_all_button.configure(state="normal" if has_item else "disabled")

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

    def create_list_row(self, parent, title: str, subtitle: str, selected: bool, command, menu_handler) -> ctk.CTkFrame:
        row_bg = TOKENS["accent_soft"] if selected else TOKENS["panel_alt"]
        row_hover = "#0b5aa7" if selected else TOKENS["panel_soft"]
        row = ctk.CTkFrame(parent, fg_color=row_bg, corner_radius=4, height=30, border_width=1 if selected else 0, border_color=TOKENS["accent"] if selected else TOKENS["panel_alt"])
        row.grid_propagate(False)
        accent = ctk.CTkFrame(row, fg_color=TOKENS["accent"] if selected else TOKENS["panel_soft"], width=2, corner_radius=2)
        accent.place(x=0, rely=0.08, relheight=0.84)
        row_text = f"{title}    {subtitle}"
        text_button = ctk.CTkButton(row, text=row_text, command=command, fg_color=row_bg, hover_color=row_hover, text_color=TOKENS["selected_text"], width=10, border_width=0, corner_radius=3, font=ctk.CTkFont(size=12, weight="bold"), anchor="w", height=26)
        text_button.place(x=10, y=2, relwidth=0.93)
        for widget in (row, accent, text_button):
            widget.bind("<Button-1>", lambda _event, cb=command: cb(), add="+")
            widget.bind("<Double-Button-1>", lambda _event, cb=command: cb(), add="+")
            widget.bind("<Button-3>", menu_handler, add="+")
        return row

    def create_command_row(self, parent, summary_text: str, selected: bool, command, menu_handler) -> ctk.CTkFrame:
        row_bg = TOKENS["accent_soft"] if selected else TOKENS["panel_alt"]
        row_hover = "#0b5aa7" if selected else TOKENS["panel_soft"]
        row = ctk.CTkFrame(parent, fg_color=row_bg, corner_radius=4, height=34, border_width=1 if selected else 0, border_color=TOKENS["accent"] if selected else TOKENS["panel_alt"])
        row.grid_propagate(False)
        guide = ctk.CTkFrame(row, fg_color=TOKENS["accent"] if selected else "#2d3642", width=2, corner_radius=2)
        guide.place(x=0, rely=0.08, relheight=0.84)
        summary_label = ctk.CTkLabel(row, text=summary_text, text_color=TOKENS["selected_text"], font=ctk.CTkFont(size=11, weight="bold"), anchor="w")
        summary_label.place(x=10, rely=0.15)
        for widget in (row, guide, summary_label):
            widget.bind("<Button-1>", lambda _event, cb=command: cb(), add="+")
            widget.bind("<Double-Button-1>", lambda _event, cb=command: cb(), add="+")
            widget.bind("<Button-3>", menu_handler, add="+")
        return row

    def render_groups(self) -> None:
        self.clear_frame(self.group_scroll)
        groups = self.app.data.get("groups", [])
        if not groups:
            ctk.CTkLabel(self.group_scroll, text="No groups yet", text_color=TOKENS["text_dim"], font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=0, padx=10, pady=14, sticky="w")
            return
        for index, group in enumerate(groups):
            row = self.create_list_row(self.group_scroll, group["name"], f"{len(group.get('items', []))} items", group["id"] == self.selected_group_id, lambda gid=group["id"]: self.select_group(gid), lambda event, gid=group["id"]: self.on_group_menu(event, gid))
            row.grid(row=index, column=0, padx=3, pady=1, sticky="ew")

    def render_items(self) -> None:
        self.clear_frame(self.item_scroll)
        group = self.get_selected_group()
        self.item_title.configure(text=f"ITEMS | {group['name']}" if group else "ITEMS")
        if not group:
            ctk.CTkLabel(self.item_scroll, text="Select a group", text_color=TOKENS["text_dim"], font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=0, padx=10, pady=14, sticky="w")
            return
        items = group.get("items", [])
        if not items:
            ctk.CTkLabel(self.item_scroll, text="No items", text_color=TOKENS["text_dim"], font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=0, padx=10, pady=14, sticky="w")
            return
        for index, item in enumerate(items):
            row = self.create_list_row(self.item_scroll, item["name"], f"{len(item.get('commands', []))} commands", item["id"] == self.selected_item_id, lambda iid=item["id"]: self.select_item(iid), lambda event, iid=item["id"]: self.on_item_menu(event, iid))
            row.grid(row=index, column=0, padx=3, pady=1, sticky="ew")

    def render_commands(self) -> None:
        self.clear_frame(self.command_scroll)
        group = self.get_selected_group()
        item = self.get_selected_item()
        if not group or not item:
            self.command_title.configure(text="No Selection")
            self.command_subtitle.configure(text="Choose a group and item to inspect commands.")
            self.render_preview([])
            ctk.CTkLabel(self.command_scroll, text="Commands will appear here", text_color=TOKENS["text_dim"], font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=0, padx=10, pady=14, sticky="w")
            return
        commands = item.get("commands", [])
        self.command_title.configure(text=item["name"])
        self.command_subtitle.configure(text=f"{group['name']} | {len(commands)} commands")
        if not commands:
            self.render_preview([])
            ctk.CTkLabel(self.command_scroll, text="No commands yet", text_color=TOKENS["text_dim"], font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=0, padx=10, pady=14, sticky="w")
            return
        for index, entry in enumerate(commands):
            summary_text, _command_line = self.summarize_command(entry["command"], index + 1)
            summary_text = summary_text if _command_line else summary_text
            row = self.create_command_row(self.command_scroll, f"{summary_text} | {_command_line}" if _command_line else summary_text, entry["id"] == self.selected_command_id, lambda cid=entry["id"]: self.select_command(cid), lambda event, cid=entry["id"]: self.on_command_menu(event, cid))
            row.grid(row=index, column=0, padx=3, pady=1, sticky="ew")
        self.render_preview(commands)

    def render_preview(self, commands: List[Dict[str, str]]) -> None:
        self.command_preview.configure(state="normal")
        self.command_preview.delete("1.0", "end")
        self.preview_line_map = {}
        self.preview_command_ranges = {}
        for index, command in enumerate(commands):
            command_text = self.command_preview_text(command["command"]).rstrip()
            start_index = self.command_preview.index("end-1c")
            if command_text:
                self.command_preview.insert("end", command_text)
            end_index = self.command_preview.index(f"{start_index} + {len(command_text)}c")
            self.preview_command_ranges[command["id"]] = (start_index, end_index)
            if index < len(commands) - 1:
                self.command_preview.insert("end", "\n\n")
        self.preview_selected_line_number = None
        self.preview_selected_line_text = None
        self.apply_preview_command_highlight(self.selected_command_id)

    def select_preview_line(self, line_number: int) -> None:
        _ = line_number
        return

    def clear_preview_command_highlight(self) -> None:
        self.command_preview.tag_remove("command_block_highlight", "1.0", "end")

    def apply_preview_command_highlight(self, command_id: Optional[str]) -> None:
        self.clear_preview_command_highlight()
        if not command_id:
            return
        span = self.preview_command_ranges.get(command_id)
        if span is None:
            return
        start, end = span
        if start == end:
            return
        self.command_preview.tag_add("command_block_highlight", start, end)
        try:
            self.command_preview.see(start)
        except Exception:
            pass

    def render_commands_list_selection_only(self) -> None:
        self.clear_frame(self.command_scroll)
        item = self.get_selected_item()
        if not item:
            return
        commands = item.get("commands", [])
        for index, entry in enumerate(commands):
            row = self.create_command_row(self.command_scroll, index + 1, entry["command"], entry["id"] == self.selected_command_id, lambda cid=entry["id"]: self.select_command(cid), lambda event, cid=entry["id"]: self.on_command_menu(event, cid))
            row.grid(row=index, column=0, padx=3, pady=1, sticky="ew")

    def on_preview_click(self, _event: tk.Event):
        self.command_preview.focus_set()
        return None

    def on_preview_right_click(self, event: tk.Event) -> str:
        self.command_preview.focus_set()
        has_selection = self.has_preview_selection()
        try:
            self.preview_menu.entryconfigure(0, state="normal" if has_selection else "disabled")
        except Exception:
            pass
        try:
            self.preview_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.preview_menu.grab_release()
        return "break"

    def insert_preview_line(self) -> None:
        self.insert_selected_preview_text()

    def copy_preview_line(self) -> None:
        self.copy_preview_selection()

    def run_preview_line(self) -> None:
        self.insert_selected_preview_text(run=True)

    def copy_preview_selection(self) -> None:
        selected = self.get_preview_selection()
        if selected:
            self.command_preview.clipboard_clear()
            self.command_preview.clipboard_append(selected)
            self.command_preview.update_idletasks()

    def select_all_preview(self) -> None:
        self.command_preview.tag_add("sel", "1.0", "end-1c")
        self.command_preview.mark_set("insert", "1.0")
        self.command_preview.see("1.0")

    def on_preview_copy_shortcut(self, _event: tk.Event) -> str:
        self.copy_preview_selection()
        return "break"

    def on_preview_select_all_shortcut(self, _event: tk.Event) -> str:
        self.select_all_preview()
        return "break"

    def insert_selected_preview_text(self, run: bool = False) -> None:
        if self.preview_selected_line_text is None:
            selected = self.get_preview_selection()
        else:
            selected = self.preview_selected_line_text
        if not selected:
            return
        if run:
            self.app.send_to_active_terminal(selected, "Preview / Selection")
        else:
            self.app.insert_into_active_terminal(selected)

    def has_preview_selection(self) -> bool:
        try:
            return bool(self.command_preview.tag_ranges("sel"))
        except Exception:
            return False

    def get_preview_selection(self) -> str:
        if not self.has_preview_selection():
            return ""
        try:
            return self.command_preview.get("sel.first", "sel.last")
        except Exception:
            return ""

    def select_group(self, group_id: str) -> None:
        self.selected_group_id = group_id
        group = self.get_selected_group()
        self.selected_item_id = group["items"][0]["id"] if group and group.get("items") else None
        item = self.get_selected_item()
        self.selected_command_id = item["commands"][0]["id"] if item and item.get("commands") else None
        self.refresh_all()

    def select_item(self, item_id: str) -> None:
        group, item = self.find_item_and_parent(item_id)
        if not group or not item:
            return
        self.selected_group_id = group["id"]
        self.selected_item_id = item["id"]
        self.selected_command_id = item["commands"][0]["id"] if item.get("commands") else None
        self.refresh_all()

    def select_command(self, command_id: str) -> None:
        _group, item, command = self.find_command_and_parent(command_id)
        if not item or not command:
            return
        self.selected_item_id = item["id"]
        self.selected_command_id = command["id"]
        self.refresh_all()

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
        self.app.data["groups"].append({"id": __import__('uuid').uuid4().hex, "name": name, "items": []})
        self.selected_group_id = self.app.data["groups"][-1]["id"]
        self.selected_item_id = None
        self.selected_command_id = None
        self.app.save_data()
        self.refresh_all()

    def rename_selected_group(self) -> None:
        if self.selected_group_id:
            group = next((group for group in self.app.data.get("groups", []) if group["id"] == self.selected_group_id), None)
            if not group:
                return
            new_name = SingleLineDialog.ask(self, "Rename Group", "Enter new group name:", group["name"])
            if new_name:
                group["name"] = new_name
                self.app.save_data()
                self.refresh_all()

    def delete_selected_group(self) -> None:
        if not self.selected_group_id:
            return
        groups = self.app.data.get("groups", [])
        target = next((group for group in groups if group["id"] == self.selected_group_id), None)
        if not target:
            return
        if not messagebox.askyesno("Delete Group", f"Delete group '{target['name']}'?\nAll nested items and commands will be removed.", parent=self):
            return
        self.app.data["groups"] = [group for group in groups if group["id"] != self.selected_group_id]
        self.selected_group_id = None
        self.selected_item_id = None
        self.selected_command_id = None
        self.app.save_data()
        self.refresh_all()

    def add_item(self) -> None:
        group = self.get_selected_group()
        if not group:
            messagebox.showwarning("Warning", "Please select a group first.", parent=self)
            return
        name = SingleLineDialog.ask(self, "New Item", "Enter item name:")
        if not name:
            return
        new_item = {"id": __import__('uuid').uuid4().hex, "name": name, "commands": []}
        group["items"].append(new_item)
        self.selected_item_id = new_item["id"]
        self.selected_command_id = None
        self.app.save_data()
        self.refresh_all()

    def rename_selected_item(self) -> None:
        if self.selected_item_id:
            _group, item = self.find_item_and_parent(self.selected_item_id)
            if not item:
                return
            new_name = SingleLineDialog.ask(self, "Rename Item", "Enter new item name:", item["name"])
            if new_name:
                item["name"] = new_name
                self.app.save_data()
                self.refresh_all()

    def delete_selected_item(self) -> None:
        if not self.selected_item_id:
            return
        group, item = self.find_item_and_parent(self.selected_item_id)
        if not group or not item:
            return
        if not messagebox.askyesno("Delete Item", f"Delete item '{item['name']}'?\nAll nested commands will be removed.", parent=self):
            return
        group["items"] = [candidate for candidate in group.get("items", []) if candidate["id"] != self.selected_item_id]
        self.selected_item_id = None
        self.selected_command_id = None
        self.app.save_data()
        self.refresh_all()

    def add_command(self) -> None:
        item = self.get_selected_item()
        if not item:
            messagebox.showwarning("Warning", "Please select an item first.", parent=self)
            return
        command_result = CommandDialog.ask(self, "Add Commands")
        if not command_result:
            return
        command_text, save_mode = command_result
        if save_mode == "one":
            new_command = {"id": uuid.uuid4().hex, "command": command_text}
            item["commands"].append(new_command)
            self.selected_command_id = new_command["id"]
        else:
            new_commands = self.insert_command_texts(item, command_text)
            if not new_commands:
                messagebox.showwarning("Warning", "No valid commands were found.", parent=self)
                return
            self.selected_command_id = new_commands[0]["id"]
        self.app.save_data()
        self.refresh_all()

    def edit_selected_command(self) -> None:
        if self.selected_command_id:
            _group, item, command = self.find_command_and_parent(self.selected_command_id)
            if not item or not command:
                return
            command_result = CommandDialog.ask(self, "Edit Commands", command["command"])
            if not command_result:
                return
            new_text, save_mode = command_result
            if save_mode == "one":
                command["command"] = new_text
                self.selected_command_id = command["id"]
            else:
                new_commands = self.replace_command_text(item, command["id"], new_text)
                if not new_commands:
                    messagebox.showwarning("Warning", "No valid commands were found.", parent=self)
                    return
                self.selected_command_id = new_commands[0]["id"]
            self.app.save_data()
            self.refresh_all()

    def delete_selected_command(self) -> None:
        if not self.selected_command_id:
            return
        _group, item, command = self.find_command_and_parent(self.selected_command_id)
        if not item or not command:
            return
        if not messagebox.askyesno("Delete Command", "Delete this command?", parent=self):
            return
        item["commands"] = [candidate for candidate in item.get("commands", []) if candidate["id"] != self.selected_command_id]
        self.selected_command_id = item["commands"][0]["id"] if item.get("commands") else None
        self.app.save_data()
        self.refresh_all()

    def copy_selected_command(self) -> None:
        command = self.get_selected_command()
        if command:
            self.copy_command(self.command_preview_text(command["command"]))

    def insert_selected_command(self) -> None:
        command = self.get_selected_command()
        if not command:
            return
        self.app.insert_into_active_terminal(self.command_preview_text(command["command"]))

    def copy_command(self, command_text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(command_text)

    def run_selected_command(self) -> None:
        item = self.get_selected_item()
        command = self.get_selected_command()
        if not item or not command:
            return
        commands = item.get("commands", [])
        index = next((idx + 1 for idx, entry in enumerate(commands) if entry["id"] == command["id"]), 1)
        self.app.send_to_active_terminal(self.command_preview_text(command["command"]), f"{item['name']} / Command {index}")

    def run_all_commands(self) -> None:
        item = self.get_selected_item()
        if not item:
            messagebox.showwarning("Warning", "Please select an item first.", parent=self)
            return
        commands = item.get("commands", [])
        if not commands:
            return
        for index, command in enumerate(commands, start=1):
            self.app.send_to_active_terminal(self.command_preview_text(command["command"]), f"{item['name']} / Command {index}")

    def on_close(self) -> None:
        self.withdraw()
