from tkinter import messagebox
from typing import Optional, Tuple

from theme.bootstrap import ctk


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
        self.result: Optional[Tuple[str, str]] = None
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
            text="PowerShell Commands",
            font=ctk.CTkFont(size=15, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, padx=16, pady=(16, 8), sticky="ew")
        self.textbox = ctk.CTkTextbox(container, wrap="word")
        self.textbox.grid(row=1, column=0, padx=16, pady=(0, 12), sticky="nsew")
        if initial_value:
            self.textbox.insert("1.0", initial_value)
        ctk.CTkLabel(
            container,
            text="Paste one command per line. Blank lines are ignored. Lines starting with # can be skipped.",
            anchor="w",
            text_color=("gray35", "gray70"),
        ).grid(row=2, column=0, padx=16, pady=(0, 12), sticky="ew")
        button_frame = ctk.CTkFrame(container, fg_color="transparent")
        button_frame.grid(row=3, column=0, padx=16, pady=(0, 16), sticky="e")
        ctk.CTkButton(button_frame, text="Cancel", width=90, command=self.on_cancel).pack(side="right", padx=(8, 0))
        ctk.CTkButton(button_frame, text="Save as Multiple Commands", width=180, command=lambda: self.on_save("multiple")).pack(side="right", padx=(8, 0))
        ctk.CTkButton(button_frame, text="Save as One Command", width=150, command=lambda: self.on_save("one")).pack(side="right")
        self.bind("<Escape>", lambda _event: self.on_cancel())
        self.after(50, self._focus_textbox)

    def _focus_textbox(self) -> None:
        self.textbox.focus_set()

    def on_save(self, mode: str) -> None:
        value = self.textbox.get("1.0", "end").rstrip("\n")
        if not value.strip():
            messagebox.showwarning("Warning", "Command content cannot be empty.", parent=self)
            return
        self.result = (value, mode)
        self.destroy()

    def on_cancel(self) -> None:
        self.result = None
        self.destroy()

    @classmethod
    def ask(cls, master: ctk.CTk, title: str, initial_value: str = "") -> Optional[Tuple[str, str]]:
        dialog = cls(master, title, initial_value)
        dialog.wait_window()
        return dialog.result
