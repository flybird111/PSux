from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QTextCursor, QTextFormat
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from quick_commands.manager import DEFAULT_CATEGORY, QuickCommandsManager
from quick_commands.models import QuickCommand


def quick_commands_stylesheet() -> str:
    return """
        QDialog {
            background-color: #10131a;
            color: #eef2f7;
        }
        QListWidget, QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {
            background-color: #0b0e14;
            color: #eef2f7;
            border: 1px solid #28303a;
            border-radius: 8px;
            padding: 6px;
            selection-background-color: #17314a;
            selection-color: #f8fbff;
        }
        QComboBox::drop-down {
            border: none;
            width: 18px;
        }
        QComboBox QAbstractItemView {
            background-color: #0b0e14;
            color: #eef2f7;
            border: 1px solid #28303a;
            selection-background-color: #17314a;
            selection-color: #f8fbff;
            outline: none;
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


def command_block_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return lines


class CommandBlockView(QPlainTextEdit):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self._highlight_current_line()

    def current_line_text(self) -> str:
        return self.textCursor().block().text().strip()

    def _highlight_current_line(self) -> None:
        selection = QTextEdit.ExtraSelection()
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        selection.format.setProperty(QTextFormat.FullWidthSelection, True)
        # Use an explicit dark highlight instead of palette().alternateBase():
        # some Windows themes return a near-white alternateBase, which makes the
        # white terminal-style text unreadable inside the command block.
        selection.format.setBackground(QColor("#182231"))
        self.setExtraSelections([selection])


class QuickCommandEditorDialog(QDialog):
    def __init__(self, categories: list[str], command: QuickCommand | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Quick Command" if command else "New Quick Command")
        self.resize(620, 420)

        self.name_input = QLineEdit(command.name if command else "")
        self.category_input = QComboBox()
        self.category_input.setEditable(True)
        self.category_input.addItems(categories)
        self.category_input.setCurrentText(command.category if command else (categories[0] if categories else DEFAULT_CATEGORY))
        self.command_input = QPlainTextEdit(command.command if command else "")
        self.command_input.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.note_input = QTextEdit(command.note if command else "")
        self.note_input.setAcceptRichText(False)

        save_button = QPushButton("Save")
        save_button.clicked.connect(self.accept)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)

        form = QFormLayout()
        form.addRow("Name", self.name_input)
        form.addRow("Category", self.category_input)
        form.addRow("Command Block", self.command_input)
        form.addRow("Note", self.note_input)

        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(cancel_button)
        actions.addWidget(save_button)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(actions)

        self.setStyleSheet(quick_commands_stylesheet())

    def get_payload(self) -> tuple[str, str, str, str]:
        return (
            self.name_input.text().strip(),
            self.category_input.currentText().strip(),
            self.command_input.toPlainText().strip(),
            self.note_input.toPlainText().strip(),
        )


class CategoryManagerDialog(QDialog):
    def __init__(self, manager: QuickCommandsManager, parent=None) -> None:
        super().__init__(parent)
        self._manager = manager
        self.setWindowTitle("Manage Categories")
        self.resize(420, 360)

        self.category_list = QListWidget()
        self.category_list.setSelectionMode(QAbstractItemView.SingleSelection)

        add_button = QPushButton("Add")
        add_button.clicked.connect(self._add_category)
        rename_button = QPushButton("Rename")
        rename_button.clicked.connect(self._rename_category)
        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(self._delete_category)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)

        actions = QHBoxLayout()
        actions.addWidget(add_button)
        actions.addWidget(rename_button)
        actions.addWidget(delete_button)
        actions.addStretch(1)
        actions.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Categories"))
        layout.addWidget(self.category_list, 1)
        layout.addLayout(actions)

        self.setStyleSheet(quick_commands_stylesheet())
        self.refresh()

    def refresh(self) -> None:
        self.category_list.clear()
        for category in self._manager.categories:
            self.category_list.addItem(category)
        if self.category_list.count():
            self.category_list.setCurrentRow(0)

    def _selected_category(self) -> str | None:
        item = self.category_list.currentItem()
        return item.text() if item is not None else None

    def _add_category(self) -> None:
        name, accepted = QInputDialog.getText(self, "New Category", "Category name")
        if not accepted or not name.strip():
            return
        self._manager.ensure_category(name)
        self._manager.save()
        self.refresh()

    def _rename_category(self) -> None:
        current = self._selected_category()
        if current is None:
            return
        new_name, accepted = QInputDialog.getText(self, "Rename Category", "Category name", text=current)
        if not accepted or not new_name.strip():
            return
        try:
            renamed = self._manager.rename_category(current, new_name)
        except ValueError as exc:
            QMessageBox.warning(self, "Categories", str(exc))
            return
        self.refresh()
        matches = self.category_list.findItems(renamed, Qt.MatchExactly)
        if matches:
            self.category_list.setCurrentItem(matches[0])

    def _delete_category(self) -> None:
        current = self._selected_category()
        if current is None:
            return
        fallback_choices = [category for category in self._manager.categories if category != current]
        fallback, accepted = QInputDialog.getItem(
            self,
            "Delete Category",
            f"Move commands from '{current}' to:",
            fallback_choices,
            0,
            False,
        )
        if not accepted:
            return
        try:
            self._manager.delete_category(current, fallback)
        except ValueError as exc:
            QMessageBox.warning(self, "Categories", str(exc))
            return
        self.refresh()


class QuickCommandsDialog(QDialog):
    def __init__(
        self,
        manager: QuickCommandsManager,
        insert_handler: Callable[[str], None],
        execute_handler: Callable[[list[str]], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._manager = manager
        self._insert_handler = insert_handler
        self._execute_handler = execute_handler
        self._selected_id: str | None = None

        self.setWindowTitle("Quick Commands")
        self.resize(980, 580)
        self.setModal(True)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by name, category, or note")
        self.search_input.textChanged.connect(self.refresh_list)

        self.category_filter = QComboBox()
        self.category_filter.currentIndexChanged.connect(self.refresh_list)

        self.commands_list = QListWidget()
        self.commands_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.commands_list.currentItemChanged.connect(self._handle_selection_changed)
        self.commands_list.itemDoubleClicked.connect(lambda _: self._run_all_selected())

        self.name_label = QLabel("Select a quick command")
        self.category_label = QLabel("")
        self.current_line_label = QLabel("Line: none")
        self.command_preview = CommandBlockView()
        self.command_preview.cursorPositionChanged.connect(self._update_current_line_label)
        self.note_preview = QTextEdit()
        self.note_preview.setReadOnly(True)
        self.note_preview.setAcceptRichText(False)

        self.insert_button = QPushButton("Insert")
        self.insert_button.clicked.connect(self._insert_selected)
        self.run_all_button = QPushButton("Run All")
        self.run_all_button.clicked.connect(self._run_all_selected)
        self.run_line_button = QPushButton("Run Line")
        self.run_line_button.clicked.connect(self._run_current_line)
        self.copy_button = QPushButton("Copy")
        self.copy_button.clicked.connect(self._copy_selected)
        self.new_button = QPushButton("New")
        self.new_button.clicked.connect(self._new_command)
        self.edit_button = QPushButton("Edit")
        self.edit_button.clicked.connect(self._edit_selected)
        self.categories_button = QPushButton("Categories")
        self.categories_button.clicked.connect(self._manage_categories)
        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self._delete_selected)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.accept)

        self._build_layout()
        self._refresh_category_filter()
        self.refresh_list()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Quick Commands"))
        toolbar.addWidget(self.category_filter, 0)
        toolbar.addWidget(self.search_input, 1)
        toolbar.addWidget(self.categories_button, 0)

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
        detail_layout.addWidget(self.current_line_label)
        detail_layout.addWidget(QLabel("Command Block"))
        detail_layout.addWidget(self.command_preview, 3)
        detail_layout.addWidget(QLabel("Note"))
        detail_layout.addWidget(self.note_preview, 2)

        content.addWidget(list_panel, 0, 0)
        content.addWidget(detail_panel, 0, 1)
        content.setColumnStretch(0, 3)
        content.setColumnStretch(1, 5)

        actions = QHBoxLayout()
        actions.addWidget(self.insert_button)
        actions.addWidget(self.run_all_button)
        actions.addWidget(self.run_line_button)
        actions.addWidget(self.copy_button)
        actions.addStretch(1)
        actions.addWidget(self.new_button)
        actions.addWidget(self.edit_button)
        actions.addWidget(self.delete_button)
        actions.addWidget(self.close_button)

        root.addLayout(toolbar)
        root.addLayout(content, 1)
        root.addLayout(actions)

        self.setStyleSheet(quick_commands_stylesheet())

    def refresh_list(self) -> None:
        query = self.search_input.text().strip()
        selected_id = self._selected_id
        category = self.category_filter.currentText() or "All"
        self.commands_list.clear()

        for command in self._manager.search(query, category):
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

    def _refresh_category_filter(self, selected: str = "All") -> None:
        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        self.category_filter.addItem("All")
        self.category_filter.addItems(self._manager.categories)
        index = self.category_filter.findText(selected, Qt.MatchExactly)
        self.category_filter.setCurrentIndex(index if index >= 0 else 0)
        self.category_filter.blockSignals(False)

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
        self._update_current_line_label()

    def _selected_command(self) -> QuickCommand | None:
        if self._selected_id is None:
            return None
        return self._manager.get(self._selected_id)

    def _insert_selected(self) -> None:
        command = self._selected_command()
        if command is None:
            return
        self._insert_handler(command.command)

    def _run_all_selected(self) -> None:
        command = self._selected_command()
        if command is None:
            return
        lines = command_block_lines(command.command)
        if not lines:
            QMessageBox.information(self, "Quick Commands", "This command block has no runnable lines.")
            return
        self._execute_handler(lines)

    def _run_current_line(self) -> None:
        command = self._selected_command()
        if command is None:
            return
        del command
        line = self.command_preview.current_line_text()
        if not line or line.startswith("#"):
            QMessageBox.information(self, "Quick Commands", "Select a non-empty, non-comment line to run.")
            return
        self._execute_handler([line])

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
        self._refresh_category_filter(self.category_filter.currentText() or "All")
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
        self._refresh_category_filter(self.category_filter.currentText() or "All")
        self.refresh_list()

    def _manage_categories(self) -> None:
        dialog = CategoryManagerDialog(self._manager, parent=self)
        dialog.exec()
        selected = self.category_filter.currentText() or "All"
        if selected != "All" and selected not in self._manager.categories:
            selected = "All"
        self._refresh_category_filter(selected)
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

    def _update_current_line_label(self) -> None:
        line = self.command_preview.current_line_text()
        if not line:
            self.current_line_label.setText("Line: empty")
            return
        prefix = "comment" if line.startswith("#") else "ready"
        self.current_line_label.setText(f"Line: {prefix} | {line[:96]}")

    def _clear_details(self) -> None:
        self.name_label.setText("Select a quick command")
        self.category_label.clear()
        self.current_line_label.setText("Line: none")
        self.command_preview.clear()
        self.note_preview.clear()
