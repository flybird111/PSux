import os
import tkinter as tk
from typing import List, Optional, Tuple, TYPE_CHECKING

from theme.bootstrap import ctk
from terminal.embedded_terminal import EmbeddedTerminal

if TYPE_CHECKING:
    from main import QuickCommandApp


class TerminalHost(ctk.CTkFrame):
    def __init__(self, master: ctk.CTkFrame, workspace: "TerminalWorkspace", initial_cwd: Optional[str] = None) -> None:
        super().__init__(master, corner_radius=0, fg_color="#0f141b")
        self.workspace = workspace
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.terminal = EmbeddedTerminal(self, on_activate=lambda: self.workspace.set_active_host(self), initial_cwd=initial_cwd)
        self.terminal.grid(row=0, column=0, padx=0, pady=0, sticky="nsew")
        self.terminal.set_context_menu_provider(self.populate_context_menu)
        self._bind_activate_events()

    def _bind_activate_events(self) -> None:
        def activate(_event: tk.Event) -> str:
            self.workspace.set_active_host(self)
            self.terminal.text_widget.focus_set()
            return "break"
        for widget in (self.terminal,):
            widget.bind("<Button-1>", activate, add="+")
            widget.bind("<Button-3>", self.show_pane_menu, add="+")

    def populate_context_menu(self, menu: tk.Menu) -> None:
        menu.add_separator()
        menu.add_command(label="Quick Commands", command=self.workspace.app.open_quick_command_window)
        menu.add_separator()
        menu.add_command(label="Split Right", command=lambda: self.workspace.split_host(self, "vertical"))
        menu.add_command(label="Split Down", command=lambda: self.workspace.split_host(self, "horizontal"))
        menu.add_command(label="Clear Buffer", command=self.clear_buffer)
        close_state = "normal" if len(self.workspace.iter_hosts()) > 1 else "disabled"
        menu.add_command(label="Close Pane", command=lambda: self.workspace.close_host(self), state=close_state)

    def show_pane_menu(self, event: tk.Event) -> str:
        self.workspace.set_active_host(self)
        menu = tk.Menu(self, tearoff=0)
        self.populate_context_menu(menu)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def clear_buffer(self) -> None:
        self.workspace.set_active_host(self)
        self.terminal.send_command("Clear-Host")

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

    def split_host(self, host: Optional[TerminalHost], orientation: str) -> None:
        if host is None:
            return
        old_host = host
        inherited_cwd = old_host.terminal.current_directory or os.getcwd()
        parent, index = self._find_pane_parent(old_host)
        nested = tk.PanedWindow(parent if parent is not None else self, orient=tk.VERTICAL if orientation == "horizontal" else tk.HORIZONTAL, sashrelief=tk.RAISED, sashwidth=6, bd=0, bg="#3a4150")
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

    def split_active(self, orientation: str) -> None:
        self.split_host(self.active_host, orientation)

    def close_host(self, host: Optional[TerminalHost]) -> None:
        if host is None:
            return
        if len(self.iter_hosts()) == 1:
            host.clear_buffer()
            return
        parent, index = self._find_pane_parent(host)
        if not isinstance(parent, tk.PanedWindow) or index is None:
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

    def close_active(self) -> None:
        self.close_host(self.active_host)

    def get_active_terminal(self) -> Optional[EmbeddedTerminal]:
        if self.active_host is None:
            return None
        return self.active_host.terminal

    def get_active_cwd(self) -> str:
        terminal = self.get_active_terminal()
        if terminal is None:
            return os.getcwd()
        return terminal.current_directory or os.getcwd()
