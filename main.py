import tkinter as tk
import traceback
from tkinter import messagebox
from typing import Any, Dict, Optional

from models.storage import DataStore
from quick_commands.window import QuickCommandWindow
from terminal.workspace import TerminalWorkspace
from theme.bootstrap import app_directory, ctk, write_startup_log


class QuickCommandApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.report_callback_exception = self.on_tk_exception
        self.base_dir = app_directory()
        self.data_file = str((__import__('pathlib').Path(self.base_dir) / 'data.json'))
        self.store = DataStore(self.data_file)
        self.data = self.store.load()
        self.quick_command_window: Optional[QuickCommandWindow] = None
        self.active_terminal = None
        self.tab_counter = 0
        self.tab_workspaces: Dict[str, Dict[str, Any]] = {}
        self.active_tab_id: Optional[str] = None
        self.tab_menu = tk.Menu(self, tearoff=0)
        self._tab_menu_target: Optional[str] = None

        self.title('PowerShell Workspace')
        self.geometry('1600x960')
        self.minsize(1240, 760)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.create_toolbar()
        self.create_workspace()
        self.configure_tab_menu()
        self.bind_all('<Control-Shift-P>', self.open_quick_command_shortcut, add='+')
        self.bind_all('<Control-Shift-p>', self.open_quick_command_shortcut, add='+')
        self.create_initial_tab()
        self.deiconify()

    def create_toolbar(self) -> None:
        self.toolbar = ctk.CTkFrame(self, height=34, corner_radius=0, fg_color='#111821')
        self.toolbar.grid(row=0, column=0, sticky='ew')
        self.toolbar.grid_columnconfigure(0, weight=1)
        self.tab_strip = ctk.CTkFrame(self.toolbar, corner_radius=0, fg_color='#111821')
        self.tab_strip.grid(row=0, column=0, padx=(8, 8), pady=3, sticky='w')
        self.new_tab_button = ctk.CTkButton(self.tab_strip, text='+', width=22, height=22, corner_radius=5, fg_color='#161d26', hover_color='#223042', text_color='#dbe7f2', font=ctk.CTkFont(size=12, weight='bold'), command=self.add_tab)

    def create_workspace(self) -> None:
        self.workspace_container = ctk.CTkFrame(self, corner_radius=0)
        self.workspace_container.grid(row=1, column=0, sticky='nsew')
        self.workspace_container.grid_columnconfigure(0, weight=1)
        self.workspace_container.grid_rowconfigure(0, weight=1)
        self.workspace_stack = ctk.CTkFrame(self.workspace_container, corner_radius=0, fg_color='#0f141b')
        self.workspace_stack.grid(row=0, column=0, padx=0, pady=0, sticky='nsew')
        self.workspace_stack.grid_columnconfigure(0, weight=1)
        self.workspace_stack.grid_rowconfigure(0, weight=1)

    def create_initial_tab(self) -> None:
        self.add_tab()

    def configure_tab_menu(self) -> None:
        self.tab_menu.add_command(label='Rename', command=self.rename_tab_from_menu)
        self.tab_menu.add_command(label='Duplicate', command=self.duplicate_tab_from_menu)
        self.tab_menu.add_separator()
        self.tab_menu.add_command(label='Close', command=self.close_tab_from_menu)

    def build_tab_title(self) -> str:
        self.tab_counter += 1
        return f'Tab {self.tab_counter}'

    def add_tab(self, title: Optional[str] = None, initial_cwd: Optional[str] = None) -> str:
        import uuid
        tab_id = uuid.uuid4().hex
        tab_title = title or self.build_tab_title()
        container = ctk.CTkFrame(self.workspace_stack, corner_radius=0, fg_color='#0f141b')
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(0, weight=1)
        workspace = TerminalWorkspace(container, self)
        if initial_cwd:
            terminal = workspace.get_active_terminal()
            if terminal is not None and terminal.current_directory != initial_cwd:
                terminal.current_directory = initial_cwd
                terminal.restart_shell()
        workspace.grid(row=0, column=0, sticky='nsew')
        tab_button = ctk.CTkFrame(self.tab_strip, corner_radius=5, fg_color='#161d26', border_width=1, border_color='#202833', height=26)
        tab_button.grid_columnconfigure(0, weight=1)
        tab_button.grid_propagate(False)
        tab_button.configure(width=164)
        label = ctk.CTkLabel(tab_button, text=tab_title, text_color='#c7d2df', font=ctk.CTkFont(size=12), anchor='w', cursor='hand2')
        label.grid(row=0, column=0, padx=(8, 3), pady=0, sticky='w')
        close_button = ctk.CTkButton(tab_button, text='x', width=14, height=14, corner_radius=3, fg_color='transparent', hover_color='#2b3645', text_color='#9fb0c3', font=ctk.CTkFont(size=10, weight='bold'), command=lambda tid=tab_id: self.close_tab(tid))
        close_button.grid(row=0, column=1, padx=(0, 8), pady=0, sticky='e')
        self.tab_workspaces[tab_id] = {'title': tab_title, 'container': container, 'workspace': workspace, 'tab_button': tab_button, 'label': label, 'close_button': close_button}
        tab_button.grid(row=0, column=len(self.tab_workspaces)-1, padx=(0, 3), pady=0, sticky='w')
        for widget in (tab_button, label):
            widget.bind('<Button-1>', lambda _event, tid=tab_id: self.select_tab(tid), add='+')
            widget.bind('<Button-3>', lambda event, tid=tab_id: self.show_tab_menu(event, tid), add='+')
            widget.bind('<Enter>', lambda _event, tid=tab_id: self.set_tab_hover(tid, True), add='+')
            widget.bind('<Leave>', lambda _event, tid=tab_id: self.set_tab_hover(tid, False), add='+')
        close_button.bind('<Button-3>', lambda event, tid=tab_id: self.show_tab_menu(event, tid), add='+')
        container.grid(row=0, column=0, sticky='nsew')
        container.grid_remove()
        self.select_tab(tab_id)
        return tab_id

    def refresh_tab_strip(self) -> None:
        for index, tab_id in enumerate(self.tab_workspaces.keys()):
            self.tab_workspaces[tab_id]['tab_button'].grid_configure(row=0, column=index, padx=(0, 3), pady=0, sticky='w')
        self.new_tab_button.grid(row=0, column=len(self.tab_workspaces), padx=(2, 0), pady=0, sticky='w')
        for tab_id in self.tab_workspaces.keys():
            self.refresh_tab_visual(tab_id)

    def refresh_tab_visual(self, tab_id: str) -> None:
        tab = self.tab_workspaces.get(tab_id)
        if tab is None:
            return
        selected = tab_id == self.active_tab_id
        hovered = bool(tab.get('hovered'))
        fg_color = '#1f2935' if selected else ('#18212c' if hovered else '#161d26')
        border_color = '#3b82f6' if selected else ('#2a3645' if hovered else '#202833')
        label_color = '#f2f6fb' if selected else '#c7d2df'
        close_color = '#d7e2ef' if selected else '#9fb0c3'
        tab['tab_button'].configure(fg_color=fg_color, border_color=border_color)
        tab['label'].configure(text=tab['title'], text_color=label_color)
        tab['close_button'].configure(text_color=close_color)

    def set_tab_hover(self, tab_id: str, hovered: bool) -> None:
        tab = self.tab_workspaces.get(tab_id)
        if tab is None:
            return
        tab['hovered'] = hovered
        self.refresh_tab_visual(tab_id)

    def select_tab(self, tab_id: str) -> None:
        tab = self.tab_workspaces.get(tab_id)
        if tab is None:
            return
        for other_id, other in self.tab_workspaces.items():
            if other_id == tab_id:
                other['container'].grid()
            else:
                other['container'].grid_remove()
        self.active_tab_id = tab_id
        self.refresh_tab_strip()
        self.set_active_terminal(tab['workspace'].get_active_terminal())

    def close_tab(self, tab_id: str) -> None:
        if tab_id not in self.tab_workspaces or len(self.tab_workspaces) == 1:
            return
        tab = self.tab_workspaces.pop(tab_id)
        tab['workspace'].destroy()
        tab['container'].destroy()
        tab['tab_button'].destroy()
        if self.active_tab_id == tab_id:
            next_tab_id = next(iter(self.tab_workspaces.keys()), None)
            self.active_tab_id = None
            if next_tab_id is not None:
                self.select_tab(next_tab_id)
        else:
            self.refresh_tab_strip()

    def rename_tab(self, tab_id: str) -> None:
        from ui.dialogs import SingleLineDialog
        tab = self.tab_workspaces.get(tab_id)
        if tab is None:
            return
        new_title = SingleLineDialog.ask(self, 'Rename Tab', 'Enter tab name:', tab['title'])
        if not new_title:
            return
        tab['title'] = new_title
        self.refresh_tab_visual(tab_id)

    def duplicate_tab(self, tab_id: str) -> None:
        tab = self.tab_workspaces.get(tab_id)
        if tab is None:
            return
        self.add_tab(title=f"{tab['title']} Copy", initial_cwd=tab['workspace'].get_active_cwd())

    def show_tab_menu(self, event: tk.Event, tab_id: str) -> str:
        self._tab_menu_target = tab_id
        self.select_tab(tab_id)
        try:
            self.tab_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.tab_menu.grab_release()
        return 'break'

    def rename_tab_from_menu(self) -> None:
        if self._tab_menu_target:
            self.rename_tab(self._tab_menu_target)

    def duplicate_tab_from_menu(self) -> None:
        if self._tab_menu_target:
            self.duplicate_tab(self._tab_menu_target)

    def close_tab_from_menu(self) -> None:
        if self._tab_menu_target:
            self.close_tab(self._tab_menu_target)

    def get_current_workspace(self) -> Optional[TerminalWorkspace]:
        if not self.active_tab_id:
            return None
        tab = self.tab_workspaces.get(self.active_tab_id)
        return None if tab is None else tab['workspace']

    def set_active_terminal(self, terminal) -> None:
        self.active_terminal = terminal

    def open_quick_command_shortcut(self, _event: tk.Event) -> str:
        self.open_quick_command_window()
        return 'break'

    def open_quick_command_window(self) -> None:
        window = self.quick_command_window
        if window is None or not window.winfo_exists():
            try:
                window = QuickCommandWindow(self)
            except Exception as error:
                self.quick_command_window = None
                messagebox.showerror('Quick Command', f'Failed to open Quick Command window:\n{error}', parent=self)
                return
            self.quick_command_window = window
        window.deiconify()
        window.lift()
        window.focus_force()
        window.refresh_all()

    def save_data(self) -> None:
        self.store.save(self.data)

    def send_to_active_terminal(self, command_text: str, label: str) -> None:
        if self.active_terminal is None:
            messagebox.showwarning('Warning', 'No active terminal is available.', parent=self)
            return
        self.active_terminal.send_command(command_text)

    def insert_into_active_terminal(self, text: str) -> bool:
        terminal = self.active_terminal
        if terminal is None:
            messagebox.showwarning('Warning', 'No active terminal is available.', parent=self)
            return False
        if not terminal.can_accept_input():
            messagebox.showwarning('Warning', 'The active terminal is busy. Please wait until it returns to the prompt.', parent=self)
            return False
        return terminal.insert_into_prompt(text)

    def on_tk_exception(self, exc: type[BaseException], val: BaseException, tb: Any) -> None:
        details = ''.join(traceback.format_exception(exc, val, tb))
        write_startup_log(details)
        try:
            messagebox.showerror('Quick Command', details, parent=self)
        except Exception:
            pass

    def append_status(self, message: str) -> None:
        _ = message


def main() -> None:
    write_startup_log('=== launch ===')
    try:
        app = QuickCommandApp()
        write_startup_log('app initialized')
        app.mainloop()
        write_startup_log('mainloop exited')
    except Exception:
        write_startup_log(''.join(traceback.format_exc()))
        raise
