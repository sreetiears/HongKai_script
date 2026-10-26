"""Dialog to pick a target window from the list of visible windows."""

from __future__ import annotations

import win32gui
from PyQt6 import QtCore, QtWidgets


class WindowPickerDialog(QtWidgets.QDialog):
    """Modal dialog that lists visible windows and returns the selected title."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Select Target Window")
        self.setMinimumSize(500, 400)
        self._selected_title = ""

        self._build_ui()
        self._refresh_list()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        # Filter bar
        filter_layout = QtWidgets.QHBoxLayout()
        filter_layout.addWidget(QtWidgets.QLabel("Filter:"))
        self._filter_edit = QtWidgets.QLineEdit()
        self._filter_edit.setPlaceholderText("Type to filter window titles...")
        self._filter_edit.textChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self._filter_edit)
        refresh_btn = QtWidgets.QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_list)
        filter_layout.addWidget(refresh_btn)
        layout.addLayout(filter_layout)

        # Window list
        self._list = QtWidgets.QListWidget()
        self._list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self._list.itemDoubleClicked.connect(self.accept)
        layout.addWidget(self._list)

        # Buttons
        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _refresh_list(self) -> None:
        self._list.clear()
        self._windows: list[tuple[int, str]] = []

        def callback(hwnd: int, _: object) -> bool:
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title.strip():
                    self._windows.append((hwnd, title))
            return True

        win32gui.EnumWindows(callback, None)
        # Sort alphabetically by title
        self._windows.sort(key=lambda x: x[1].lower())

        for hwnd, title in self._windows:
            item = QtWidgets.QListWidgetItem(f"{title}")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, hwnd)
            self._list.addItem(item)

    def _on_filter_changed(self, text: str) -> None:
        text_lower = text.lower()
        for i in range(self._list.count()):
            item = self._list.item(i)
            item.setHidden(text_lower not in item.text().lower())

    def accept(self) -> None:
        current = self._list.currentItem()
        if current is not None:
            self._selected_title = current.text()
        super().accept()

    @property
    def selected_title(self) -> str:
        return self._selected_title
