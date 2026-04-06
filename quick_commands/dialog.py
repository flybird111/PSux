from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from quick_commands.manager import QuickCommandsManager
from quick_commands.models import QuickCommand


class QuickCommandEditorDialog(QDialog):
    def __init__(self, categories: list[str], command: QuickCommand | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Quick Command" if command else "New Quick Command")
        self.resize(560, 360)

        self.name_input = QLineEdit(command.name if command else "")
        self.category_input = QComboBox()
        self.category_input.setEditable(True)
        self.category_input.addItems(categories)
        self.category_input.setCurrentText(command.category if command else "Custom")
        self.command_input = QTextEdit(command.command if command else "")
        self.command_input.setAcceptRichText(False)
        self.note_input = QTextEdit(command.note if command else "")
        self.note_input.setAcceptRichText(False)

        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.accept)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)

        form = QFormLayout()
        form.addRow("Name", self.name_input)
        form.addRow("Category", self.category_input)
        form.addRow("Command", self.command_input)
        form.addRow("Note", self.note_input)

        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(cancel_button)
        actions.addWidget(self.save_button)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(actions)

        self.setStyleSheet(
            """
            QDialog {
                background-color: #11141b;
                color: #eef2f7;
            }
            QLineEdit, QTextEdit, QComboBox {
                background-color: #0d1016;
                color: #eef2f7;
                border: 1px solid #29313b;
                border-radius: 6px;
                padding: 6px;
            }
            QPushButton {
                background-color: #161d27;
                color: #eef2f7;
                border: 1px solid #2a3441;
                border-radius: 6px;
                padding: 6px 12px;
            }
            """
        )

    def get_payload(self) -> tuple[str, str, str, str]:
        return (
            self.name_input.text().strip(),
            self.category_input.currentText().strip(),
            self.command_input.toPlainText().strip(),
            self.note_input.toPlainText().strip(),
        )


class QuickCommandsDialog(QDialog):
    def __init__(
        self,
        manager: QuickCommandsManager,
        insert_handler: Callable[[str], None],
        execute_handler: Callable[[str], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._manager = manager
        self._insert_handler = insert_handler
        self._execute_handler = execute_handler
        self._selected_id: str | None = None

        self.setWindowTitle("Quick Commands")
        self.resize(880, 520)
        self.setModal(True)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by name, category, or note")
        self.search_input.textChanged.connect(self.refresh_list)

        self.commands_list = QListWidget()
        self.commands_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.commands_list.currentItemChanged.connect(self._handle_selection_changed)
        self.commands_list.itemDoubleClicked.connect(lambda _: self._execute_selected())

        self.name_label = QLabel("Select a quick command")
        self.category_label = QLabel("")
        self.command_preview = QTextEdit()
        self.command_preview.setReadOnly(True)
        self.command_preview.setAcceptRichText(False)
        self.note_preview = QTextEdit()
        self.note_preview.setReadOnly(True)
        self.note_preview.setAcceptRichText(False)

        self.insert_button = QPushButton("Insert")
        self.insert_button.clicked.connect(self._insert_selected)
        self.execute_button = QPushButton("Run")
        self.execute_button.clicked.connect(self._execute_selected)
        self.copy_button = QPushButton("Copy")
        self.copy_button.clicked.connect(self._copy_selected)
        self.new_button = QPushButton("New")
        self.new_button.clicked.connect(self._new_command)
        self.edit_button = QPushButton("Edit")
        self.edit_button.clicked.connect(self._edit_selected)
        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self._delete_selected)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.accept)

        self._build_layout()
        self.refresh_list()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Quick Commands"))
        toolbar.addStretch(1)
        toolbar.addWidget(self.search_input)

        content = QGridLayout()
        content.setHorizontalSpacing(12)
        content.setVerticalSpacing(10)

        list_panel = QWidget()
        list_layout = QVBoxLayout(list_panel)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.addWidget(self.commands_list)

        detail_panel = QWidget()
        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(10)
        detail_layout.addWidget(self.name_label)
        detail_layout.addWidget(self.category_label)
        detail_layout.addWidget(QLabel("Command"))
        detail_layout.addWidget(self.command_preview, 3)
        detail_layout.addWidget(QLabel("Note"))
        detail_layout.addWidget(self.note_preview, 2)

        content.addWidget(list_panel, 0, 0)
        content.addWidget(detail_panel, 0, 1)
        content.setColumnStretch(0, 3)
        content.setColumnStretch(1, 4)

        actions = QHBoxLayout()
        actions.addWidget(self.insert_button)
        actions.addWidget(self.execute_button)
        actions.addWidget(self.copy_button)
        actions.addStretch(1)
        actions.addWidget(self.new_button)
        actions.addWidget(self.edit_button)
        actions.addWidget(self.delete_button)
        actions.addWidget(self.close_button)

        root.addLayout(toolbar)
        root.addLayout(content, 1)
        root.addLayout(actions)

        self.setStyleSheet(
            """
            QDialog {
                background-color: #10131a;
                color: #eef2f7;
            }
            QListWidget, QLineEdit, QTextEdit {
                background-color: #0b0e14;
                color: #eef2f7;
                border: 1px solid #28303a;
                border-radius: 8px;
                padding: 6px;
            }
            QListWidget::item {
                padding: 8px 10px;
                border-bottom: 1px solid #18202a;
            }
            QListWidget::item:selected {
                background-color: #17314a;
                color: #f8fbff;
            }
            QPushButton {
                background-color: #161d27;
                color: #eef2f7;
                border: 1px solid #2a3441;
                border-radius: 6px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                border-color: #4d8bca;
            }
            QLabel {
                color: #9fb0c0;
            }
            """
        )

    def refresh_list(self) -> None:
        query = self.search_input.text().strip()
        selected_id = self._selected_id
        self.commands_list.clear()

        for command in self._manager.search(query):
            item = QListWidgetItem(f"{command.name}\n{command.category}")
            item.setData(Qt.UserRole, command.id)
            item.setToolTip(command.command)
            self.commands_list.addItem(item)
            if command.id == selected_id:
                self.commands_list.setCurrentItem(item)

        if self.commands_list.count() and self.commands_list.currentItem() is None:
            self.commands_list.setCurrentRow(0)
        elif self.commands_list.count() == 0:
            self._selected_id = None
            self._clear_details()

    def _handle_selection_changed(self, current: QListWidgetItem | None, previous: QListWidgetItem | None) -> None:
        del previous
        if current is None:
            self._selected_id = None
            self._clear_details()
            return

        command_id = current.data(Qt.UserRole)
        command = self._manager.get(command_id)
        if command is None:
            self._clear_details()
            return

        self._selected_id = command.id
        self.name_label.setText(command.name)
        self.category_label.setText(command.category)
        self.command_preview.setPlainText(command.command)
        self.note_preview.setPlainText(command.note)

    def _selected_command(self) -> QuickCommand | None:
        if self._selected_id is None:
            return None
        return self._manager.get(self._selected_id)

    def _insert_selected(self) -> None:
        command = self._selected_command()
        if command is None:
            return
        self._insert_handler(command.command)
        self.accept()

    def _execute_selected(self) -> None:
        command = self._selected_command()
        if command is None:
            return
        self._execute_handler(command.command)
        self.accept()

    def _copy_selected(self) -> None:
        command = self._selected_command()
        if command is None:
            return
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(command.command)

    def _new_command(self) -> None:
        dialog = QuickCommandEditorDialog(self._manager.categories, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            quick_command = self._manager.add_command(*dialog.get_payload())
        except ValueError as exc:
            QMessageBox.warning(self, "Quick Commands", str(exc))
            return
        self._selected_id = quick_command.id
        self.refresh_list()

    def _edit_selected(self) -> None:
        command = self._selected_command()
        if command is None:
            return
        dialog = QuickCommandEditorDialog(self._manager.categories, command=command, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            self._manager.update_command(command.id, *dialog.get_payload())
        except ValueError as exc:
            QMessageBox.warning(self, "Quick Commands", str(exc))
            return
        self.refresh_list()

    def _delete_selected(self) -> None:
        command = self._selected_command()
        if command is None:
            return
        answer = QMessageBox.question(
            self,
            "Delete Quick Command",
            f"Delete '{command.name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._manager.delete_command(command.id)
        self._selected_id = None
        self.refresh_list()

    def _clear_details(self) -> None:
        self.name_label.setText("Select a quick command")
        self.category_label.clear()
        self.command_preview.clear()
        self.note_preview.clear()
