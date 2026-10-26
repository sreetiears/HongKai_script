"""Main GUI configurator window for CVAuto."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from PyQt6 import QtCore, QtGui, QtWidgets

from cvauto.core.hotkeys import HotkeyAction, HotkeyController
from cvauto.core.logging_config import setup_logging
from cvauto.core.preset import Preset, load_preset
from cvauto.core.runner import AutomationRunner
from cvauto.core.state import RunnerState

from .overlay import OverlayWindow
from .roi_calibrator import RoiCalibratorDialog
from .window_picker import WindowPickerDialog


class _GuiLogHandler(logging.Handler):
    """Logging handler that forwards formatted records to a callback."""

    def __init__(self, callback: callable) -> None:
        super().__init__()
        self.callback = callback
        self.setFormatter(logging.Formatter("[%(name)s] [%(levelname)s] %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.callback(self.format(record))
        except Exception:
            self.handleError(record)


class _RunnerThread(QtCore.QThread):
    """Runs an AutomationRunner inside its own asyncio event loop."""

    log_signal = QtCore.pyqtSignal(str)
    state_signal = QtCore.pyqtSignal(str)
    error_signal = QtCore.pyqtSignal(str)

    def __init__(self, preset_dir: str, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self.preset_dir = preset_dir
        self.runner: AutomationRunner | None = None
        self._stop_requested = False

    def run(self) -> None:
        preset = load_preset(self.preset_dir)
        self.runner = AutomationRunner(preset)

        # Install GUI log handler for this thread's runner
        handler = _GuiLogHandler(self.log_signal.emit)
        logging.getLogger("cvauto").addHandler(handler)

        self.state_signal.emit("running")
        try:
            asyncio.run(self.runner.start())
        except Exception as exc:
            self.error_signal.emit(str(exc))
        finally:
            self.state_signal.emit("stopped")
            logging.getLogger("cvauto").removeHandler(handler)

    def request_stop(self) -> None:
        if self.runner is not None:
            self.runner.request_stop()

    def request_pause(self) -> None:
        if self.runner is not None:
            self.runner.request_pause()

    def request_resume(self) -> None:
        if self.runner is not None:
            self.runner.request_resume()


class ConfiguratorWindow(QtWidgets.QMainWindow):
    """Main application window for editing presets and controlling the runner."""

    def __init__(self, initial_preset_dir: str | None = None) -> None:
        super().__init__()
        self.setWindowTitle("CVAuto Configurator")
        self.setMinimumSize(1100, 750)

        self._preset: Preset | None = None
        self._preset_dir: str | None = None
        self._modified = False
        self._runner_thread: _RunnerThread | None = None
        self._overlay: OverlayWindow | None = None
        self._hotkeys = HotkeyController()
        self._hotkeys.register()
        self._hotkey_timer = QtCore.QTimer(self)
        self._hotkey_timer.timeout.connect(self._poll_hotkeys)
        self._hotkey_timer.start(150)

        self._build_ui()
        self._build_menu()
        self._build_toolbar()

        if initial_preset_dir is not None:
            self.load_preset(initial_preset_dir)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        vlayout = QtWidgets.QVBoxLayout(central)
        vlayout.setContentsMargins(8, 8, 8, 8)

        # --- Tabs -------------------------------------------------------
        self._tabs = QtWidgets.QTabWidget()
        self._tabs.addTab(self._build_templates_tab(), "Templates")
        self._tabs.addTab(self._build_rois_tab(), "ROIs")
        self._tabs.addTab(self._build_landmarks_tab(), "Landmarks")
        self._tabs.addTab(self._build_script_tab(), "Script")
        self._tabs.addTab(self._build_settings_tab(), "Settings (JSON)")
        vlayout.addWidget(self._tabs)

        # --- Log output -------------------------------------------------
        self._log_edit = QtWidgets.QTextEdit()
        self._log_edit.setReadOnly(True)
        self._log_edit.setMaximumBlockCount(500)
        self._log_edit.setFont(QtGui.QFont("Consolas", 9))
        self._log_edit.setPlaceholderText("Log output…")
        vlayout.addWidget(self._log_edit, stretch=0)

        # Status bar
        self.statusBar().showMessage("No preset loaded")

    def _build_templates_tab(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(w)

        self._tmpl_table = QtWidgets.QTableWidget()
        self._tmpl_table.setColumnCount(4)
        self._tmpl_table.setHorizontalHeaderLabels(["Name", "Image Path", "Threshold", ""])
        self._tmpl_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._tmpl_table)

        btn_layout = QtWidgets.QHBoxLayout()
        add_btn = QtWidgets.QPushButton("Add Template…")
        add_btn.clicked.connect(self._add_template)
        btn_layout.addWidget(add_btn)
        remove_btn = QtWidgets.QPushButton("Remove Selected")
        remove_btn.clicked.connect(self._remove_selected_template)
        btn_layout.addWidget(remove_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        return w

    def _build_rois_tab(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(w)

        self._roi_table = QtWidgets.QTableWidget()
        self._roi_table.setColumnCount(7)
        self._roi_table.setHorizontalHeaderLabels(["Name", "X", "Y", "W", "H", "Templates", ""])
        self._roi_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._roi_table)

        btn_layout = QtWidgets.QHBoxLayout()
        calib_btn = QtWidgets.QPushButton("Add via Calibrator…")
        calib_btn.clicked.connect(self._open_calibrator)
        btn_layout.addWidget(calib_btn)
        manual_btn = QtWidgets.QPushButton("Add Manual…")
        manual_btn.clicked.connect(self._add_roi_manual)
        btn_layout.addWidget(manual_btn)
        remove_btn = QtWidgets.QPushButton("Remove Selected")
        remove_btn.clicked.connect(self._remove_selected_roi)
        btn_layout.addWidget(remove_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        return w

    def _build_landmarks_tab(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(w)

        self._landmark_table = QtWidgets.QTableWidget()
        self._landmark_table.setColumnCount(3)
        self._landmark_table.setHorizontalHeaderLabels(["Name", "X", "Y"])
        self._landmark_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._landmark_table)

        btn_layout = QtWidgets.QHBoxLayout()
        add_btn = QtWidgets.QPushButton("Add Landmark…")
        add_btn.clicked.connect(self._add_landmark)
        btn_layout.addWidget(add_btn)
        remove_btn = QtWidgets.QPushButton("Remove Selected")
        remove_btn.clicked.connect(self._remove_selected_landmark)
        btn_layout.addWidget(remove_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        return w

    def _build_script_tab(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(w)

        self._script_path_lbl = QtWidgets.QLabel("No script loaded")
        layout.addWidget(self._script_path_lbl)

        open_btn = QtWidgets.QPushButton("Open in External Editor")
        open_btn.clicked.connect(self._open_script_externally)
        layout.addWidget(open_btn)

        self._script_preview = QtWidgets.QTextEdit()
        self._script_preview.setReadOnly(True)
        self._script_preview.setFont(QtGui.QFont("Consolas", 9))
        layout.addWidget(self._script_preview)
        return w

    def _build_settings_tab(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(w)

        self._json_edit = QtWidgets.QTextEdit()
        self._json_edit.setFont(QtGui.QFont("Consolas", 10))
        layout.addWidget(self._json_edit)

        btn_layout = QtWidgets.QHBoxLayout()
        fmt_btn = QtWidgets.QPushButton("Format JSON")
        fmt_btn.clicked.connect(self._format_json)
        btn_layout.addWidget(fmt_btn)
        validate_btn = QtWidgets.QPushButton("Validate")
        validate_btn.clicked.connect(self._validate_json)
        btn_layout.addWidget(validate_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        return w

    def _build_menu(self) -> None:
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")

        load_action = QtGui.QAction("Load Preset…", self)
        load_action.setShortcut("Ctrl+O")
        load_action.triggered.connect(self._menu_load_preset)
        file_menu.addAction(load_action)

        save_action = QtGui.QAction("Save Preset", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._save_preset)
        file_menu.addAction(save_action)

        file_menu.addSeparator()

        exit_action = QtGui.QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

    def _build_toolbar(self) -> None:
        toolbar = QtWidgets.QToolBar("Main")
        self.addToolBar(toolbar)

        # Window picker
        toolbar.addWidget(QtWidgets.QLabel("Window:"))
        self._window_lbl = QtWidgets.QLabel("None")
        self._window_lbl.setMinimumWidth(180)
        toolbar.addWidget(self._window_lbl)

        pick_btn = QtWidgets.QPushButton("Pick…")
        pick_btn.clicked.connect(self._pick_window)
        toolbar.addWidget(pick_btn)

        toolbar.addSeparator()

        # Runner controls
        self._start_btn = QtWidgets.QPushButton("▶ Start")
        self._start_btn.clicked.connect(self._start_runner)
        toolbar.addWidget(self._start_btn)

        self._stop_btn = QtWidgets.QPushButton("⏹ Stop")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop_runner)
        toolbar.addWidget(self._stop_btn)

        self._pause_btn = QtWidgets.QPushButton("⏸ Pause")
        self._pause_btn.setCheckable(True)
        self._pause_btn.setEnabled(False)
        self._pause_btn.toggled.connect(self._toggle_pause)
        toolbar.addWidget(self._pause_btn)

        toolbar.addSeparator()

        self._overlay_btn = QtWidgets.QPushButton("Overlay")
        self._overlay_btn.setCheckable(True)
        self._overlay_btn.setEnabled(False)
        self._overlay_btn.toggled.connect(self._toggle_overlay)
        toolbar.addWidget(self._overlay_btn)

    # ------------------------------------------------------------------
    # Preset loading
    # ------------------------------------------------------------------

    def load_preset(self, preset_dir: str) -> None:
        while True:
            try:
                self._preset = load_preset(preset_dir)
                self._preset_dir = preset_dir
                break
            except FileNotFoundError as exc:
                msg = str(exc)
                # Check if this is a missing template image
                if "Template not found" in msg:
                    reply = QtWidgets.QMessageBox.question(
                        self,
                        "Missing Template",
                        f"{msg}\n\nWould you like to pick a replacement file?",
                        QtWidgets.QMessageBox.StandardButton.Yes
                        | QtWidgets.QMessageBox.StandardButton.No,
                    )
                    if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                        replacement, _ = QtWidgets.QFileDialog.getOpenFileName(
                            self,
                            "Select Replacement Template",
                            "",
                            "Images (*.png *.jpg *.jpeg *.bmp)",
                        )
                        if replacement:
                            # Update preset.json with the new path
                            self._replace_template_in_preset(preset_dir, msg, replacement)
                            continue
                    QtWidgets.QMessageBox.critical(self, "Load Error", msg)
                    return
                else:
                    QtWidgets.QMessageBox.critical(self, "Load Error", msg)
                    return
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, "Load Error", str(exc))
                return

        self.setWindowTitle(f"CVAuto Configurator – {self._preset.name}")
        self._refresh_ui_from_preset()
        self.statusBar().showMessage(f"Loaded: {preset_dir}")
        self._modified = False

    def _replace_template_in_preset(self, preset_dir: str, error_msg: str, replacement_path: str) -> None:
        """Parse the error message to find which template entry to update."""
        preset_path = Path(preset_dir) / "preset.json"
        with open(preset_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        # Extract filename from error message (last path component)
        missing_name = Path(error_msg.split(":")[-1].strip()).name
        for tmpl in config.get("templates", []):
            if Path(tmpl.get("image_path", "")).name == missing_name:
                tmpl["image_path"] = Path(replacement_path).name
                # Copy replacement into templates dir if needed
                templates_dir = Path(preset_dir) / "templates"
                dest = templates_dir / Path(replacement_path).name
                if not dest.exists():
                    import shutil
                    shutil.copy(replacement_path, dest)
                break
        with open(preset_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    def _refresh_ui_from_preset(self) -> None:
        cfg = self._preset.config if self._preset else {}

        # Window
        self._window_lbl.setText(cfg.get("window_title", "None"))

        # Templates
        templates = cfg.get("templates", [])
        self._tmpl_table.setRowCount(len(templates))
        for i, t in enumerate(templates):
            self._tmpl_table.setItem(i, 0, QtWidgets.QTableWidgetItem(t.get("name", "")))
            self._tmpl_table.setItem(i, 1, QtWidgets.QTableWidgetItem(t.get("image_path", "")))
            thresh = str(t.get("threshold", ""))
            self._tmpl_table.setItem(i, 2, QtWidgets.QTableWidgetItem(thresh))
            self._tmpl_table.setItem(i, 3, QtWidgets.QTableWidgetItem(""))

        # ROIs
        rois = cfg.get("rois", [])
        self._roi_table.setRowCount(len(rois))
        for i, r in enumerate(rois):
            rect = r.get("rect", {})
            self._roi_table.setItem(i, 0, QtWidgets.QTableWidgetItem(r.get("label", "")))
            self._roi_table.setItem(i, 1, QtWidgets.QTableWidgetItem(str(rect.get("x", 0))))
            self._roi_table.setItem(i, 2, QtWidgets.QTableWidgetItem(str(rect.get("y", 0))))
            self._roi_table.setItem(i, 3, QtWidgets.QTableWidgetItem(str(rect.get("w", 0))))
            self._roi_table.setItem(i, 4, QtWidgets.QTableWidgetItem(str(rect.get("h", 0))))
            tmpl_names = ", ".join(r.get("template_names", []))
            self._roi_table.setItem(i, 5, QtWidgets.QTableWidgetItem(tmpl_names))
            self._roi_table.setItem(i, 6, QtWidgets.QTableWidgetItem(""))

        # Landmarks
        landmarks = cfg.get("landmarks", {})
        self._landmark_table.setRowCount(len(landmarks))
        for i, (name, pt) in enumerate(landmarks.items()):
            self._landmark_table.setItem(i, 0, QtWidgets.QTableWidgetItem(name))
            self._landmark_table.setItem(i, 1, QtWidgets.QTableWidgetItem(str(pt.get("x", 0))))
            self._landmark_table.setItem(i, 2, QtWidgets.QTableWidgetItem(str(pt.get("y", 0))))

        # Script
        script_name = cfg.get("script", "script.py")
        if self._preset:
            script_path = Path(self._preset.path) / script_name
            self._script_path_lbl.setText(str(script_path))
            try:
                self._script_preview.setPlainText(script_path.read_text(encoding="utf-8"))
            except Exception:
                self._script_preview.setPlainText("(unable to read script)")

        # JSON
        self._json_edit.setPlainText(json.dumps(cfg, indent=2, ensure_ascii=False))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _menu_load_preset(self) -> None:
        directory = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Preset Directory")
        if directory:
            self.load_preset(directory)

    def _pick_window(self) -> None:
        dlg = WindowPickerDialog(self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted and dlg.selected_title:
            self._window_lbl.setText(dlg.selected_title)
            self._mark_modified()

    def _save_preset(self) -> None:
        if self._preset is None:
            return
        try:
            cfg = self._gather_config_from_ui()
            config_path = Path(self._preset.path) / "preset.json"
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
            self._modified = False
            self.statusBar().showMessage("Saved.")
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Save Error", str(exc))

    def _gather_config_from_ui(self) -> dict[str, Any]:
        # Start from current JSON text (most authoritative)
        try:
            cfg: dict[str, Any] = json.loads(self._json_edit.toPlainText())
        except json.JSONDecodeError:
            cfg = {}

        # Override with UI-derived values where applicable
        cfg["window_title"] = self._window_lbl.text()

        # Templates from table
        templates: list[dict] = []
        for i in range(self._tmpl_table.rowCount()):
            name_item = self._tmpl_table.item(i, 0)
            path_item = self._tmpl_table.item(i, 1)
            thresh_item = self._tmpl_table.item(i, 2)
            if name_item is None or path_item is None:
                continue
            t: dict[str, Any] = {"name": name_item.text(), "image_path": path_item.text()}
            if thresh_item and thresh_item.text():
                try:
                    t["threshold"] = float(thresh_item.text())
                except ValueError:
                    pass
            templates.append(t)
        cfg["templates"] = templates

        # ROIs from table
        rois: list[dict] = []
        for i in range(self._roi_table.rowCount()):
            name_item = self._roi_table.item(i, 0)
            if name_item is None:
                continue
            try:
                x = int(self._roi_table.item(i, 1).text())
                y = int(self._roi_table.item(i, 2).text())
                w = int(self._roi_table.item(i, 3).text())
                h = int(self._roi_table.item(i, 4).text())
            except (ValueError, AttributeError):
                continue
            tmpl_text = self._roi_table.item(i, 5).text() if self._roi_table.item(i, 5) else ""
            tmpl_names = [t.strip() for t in tmpl_text.split(",") if t.strip()]
            roi = {
                "label": name_item.text(),
                "rect": {"x": x, "y": y, "w": w, "h": h},
                "template_names": tmpl_names,
            }
            rois.append(roi)
        cfg["rois"] = rois

        # Landmarks from table
        landmarks: dict[str, dict] = {}
        for i in range(self._landmark_table.rowCount()):
            name_item = self._landmark_table.item(i, 0)
            if name_item is None:
                continue
            try:
                x = int(self._landmark_table.item(i, 1).text())
                y = int(self._landmark_table.item(i, 2).text())
            except (ValueError, AttributeError):
                continue
            landmarks[name_item.text()] = {"x": x, "y": y}
        cfg["landmarks"] = landmarks

        return cfg

    def _mark_modified(self) -> None:
        self._modified = True

    # ------------------------------------------------------------------
    # Template actions
    # ------------------------------------------------------------------

    def _add_template(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Template Image", "", "Images (*.png *.jpg *.jpeg *.bmp)"
        )
        if not path:
            return
        if self._preset is None:
            return
        templates_dir = Path(self._preset.template_dir)
        try:
            rel = Path(path).relative_to(templates_dir)
            image_path = str(rel).replace("\\", "/")
        except ValueError:
            # Copy into templates dir
            dest = templates_dir / Path(path).name
            import shutil
            shutil.copy(path, dest)
            image_path = dest.name

        name, ok = QtWidgets.QInputDialog.getText(self, "Template Name", "Name:")
        if not ok or not name.strip():
            return

        row = self._tmpl_table.rowCount()
        self._tmpl_table.insertRow(row)
        self._tmpl_table.setItem(row, 0, QtWidgets.QTableWidgetItem(name.strip()))
        self._tmpl_table.setItem(row, 1, QtWidgets.QTableWidgetItem(image_path))
        self._tmpl_table.setItem(row, 2, QtWidgets.QTableWidgetItem(""))
        self._mark_modified()

    def _remove_selected_template(self) -> None:
        rows = sorted({idx.row() for idx in self._tmpl_table.selectedIndexes()}, reverse=True)
        for r in rows:
            self._tmpl_table.removeRow(r)
        self._mark_modified()

    # ------------------------------------------------------------------
    # ROI actions
    # ------------------------------------------------------------------

    def _open_calibrator(self) -> None:
        title = self._window_lbl.text()
        if not title or title == "None":
            QtWidgets.QMessageBox.warning(self, "No Window", "Select a target window first.")
            return
        dlg = RoiCalibratorDialog(title, self)
        dlg.roi_created.connect(self._on_calibrated_roi)
        dlg.exec()

    def _on_calibrated_roi(self, name: str, x: int, y: int, w: int, h: int, templates: list[str]) -> None:
        row = self._roi_table.rowCount()
        self._roi_table.insertRow(row)
        self._roi_table.setItem(row, 0, QtWidgets.QTableWidgetItem(name))
        self._roi_table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(x)))
        self._roi_table.setItem(row, 2, QtWidgets.QTableWidgetItem(str(y)))
        self._roi_table.setItem(row, 3, QtWidgets.QTableWidgetItem(str(w)))
        self._roi_table.setItem(row, 4, QtWidgets.QTableWidgetItem(str(h)))
        self._roi_table.setItem(row, 5, QtWidgets.QTableWidgetItem(", ".join(templates)))
        self._mark_modified()

    def _add_roi_manual(self) -> None:
        row = self._roi_table.rowCount()
        self._roi_table.insertRow(row)
        self._roi_table.setItem(row, 0, QtWidgets.QTableWidgetItem("new_roi"))
        self._roi_table.setItem(row, 1, QtWidgets.QTableWidgetItem("0"))
        self._roi_table.setItem(row, 2, QtWidgets.QTableWidgetItem("0"))
        self._roi_table.setItem(row, 3, QtWidgets.QTableWidgetItem("100"))
        self._roi_table.setItem(row, 4, QtWidgets.QTableWidgetItem("100"))
        self._roi_table.setItem(row, 5, QtWidgets.QTableWidgetItem(""))
        self._mark_modified()

    def _remove_selected_roi(self) -> None:
        rows = sorted({idx.row() for idx in self._roi_table.selectedIndexes()}, reverse=True)
        for r in rows:
            self._roi_table.removeRow(r)
        self._mark_modified()

    # ------------------------------------------------------------------
    # Landmark actions
    # ------------------------------------------------------------------

    def _add_landmark(self) -> None:
        name, ok = QtWidgets.QInputDialog.getText(self, "Landmark Name", "Name:")
        if not ok or not name.strip():
            return
        x, ok2 = QtWidgets.QInputDialog.getInt(self, "X Coordinate", "X:", 0)
        if not ok2:
            return
        y, ok3 = QtWidgets.QInputDialog.getInt(self, "Y Coordinate", "Y:", 0)
        if not ok3:
            return
        row = self._landmark_table.rowCount()
        self._landmark_table.insertRow(row)
        self._landmark_table.setItem(row, 0, QtWidgets.QTableWidgetItem(name.strip()))
        self._landmark_table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(x)))
        self._landmark_table.setItem(row, 2, QtWidgets.QTableWidgetItem(str(y)))
        self._mark_modified()

    def _remove_selected_landmark(self) -> None:
        rows = sorted({idx.row() for idx in self._landmark_table.selectedIndexes()}, reverse=True)
        for r in rows:
            self._landmark_table.removeRow(r)
        self._mark_modified()

    # ------------------------------------------------------------------
    # Script actions
    # ------------------------------------------------------------------

    def _open_script_externally(self) -> None:
        path = self._script_path_lbl.text()
        if path and Path(path).exists():
            if sys.platform == "win32":
                os.startfile(path)
            else:
                subprocess.call(["xdg-open", path])

    # ------------------------------------------------------------------
    # Settings actions
    # ------------------------------------------------------------------

    def _format_json(self) -> None:
        try:
            cfg = json.loads(self._json_edit.toPlainText())
            self._json_edit.setPlainText(json.dumps(cfg, indent=2, ensure_ascii=False))
        except json.JSONDecodeError as exc:
            QtWidgets.QMessageBox.warning(self, "Invalid JSON", str(exc))

    def _validate_json(self) -> None:
        try:
            json.loads(self._json_edit.toPlainText())
            QtWidgets.QMessageBox.information(self, "Valid", "JSON is valid.")
        except json.JSONDecodeError as exc:
            QtWidgets.QMessageBox.warning(self, "Invalid JSON", str(exc))

    # ------------------------------------------------------------------
    # Runner control
    # ------------------------------------------------------------------

    def _start_runner(self) -> None:
        if self._preset_dir is None:
            QtWidgets.QMessageBox.warning(self, "No Preset", "Load a preset first.")
            return
        self._save_preset()  # ensure disk reflects UI
        self._runner_thread = _RunnerThread(self._preset_dir, self)
        self._runner_thread.log_signal.connect(self._append_log)
        self._runner_thread.state_signal.connect(self._on_runner_state_changed)
        self._runner_thread.error_signal.connect(self._on_runner_error)
        self._runner_thread.start()

        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._pause_btn.setEnabled(True)
        self._pause_btn.setChecked(False)
        self._overlay_btn.setEnabled(True)

    def _stop_runner(self) -> None:
        if self._runner_thread is not None:
            self._runner_thread.request_stop()

    def _toggle_pause(self, checked: bool) -> None:
        if self._runner_thread is None:
            return
        if checked:
            self._runner_thread.request_pause()
            self._pause_btn.setText("▶ Resume")
        else:
            self._runner_thread.request_resume()
            self._pause_btn.setText("⏸ Pause")

    def _toggle_overlay(self, checked: bool) -> None:
        if self._runner_thread is None or self._runner_thread.runner is None:
            return
        if checked:
            self._overlay = OverlayWindow(self._runner_thread.runner)
            self._overlay.show()
        else:
            if self._overlay is not None:
                self._overlay.close()
                self._overlay = None

    def _on_runner_state_changed(self, state: str) -> None:
        if state == "stopped":
            self._start_btn.setEnabled(True)
            self._stop_btn.setEnabled(False)
            self._pause_btn.setEnabled(False)
            self._pause_btn.setChecked(False)
            self._pause_btn.setText("⏸ Pause")
            self._overlay_btn.setEnabled(False)
            if self._overlay is not None:
                self._overlay.close()
                self._overlay = None
            self.statusBar().showMessage("Runner stopped")
        else:
            self.statusBar().showMessage("Runner running…")

    def _on_runner_error(self, message: str) -> None:
        QtWidgets.QMessageBox.critical(self, "Runner Error", message)

    def _append_log(self, text: str) -> None:
        self._log_edit.append(text)

    # ------------------------------------------------------------------
    # Hotkey polling
    # ------------------------------------------------------------------

    def _poll_hotkeys(self) -> None:
        if self._runner_thread is None or self._runner_thread.runner is None:
            return
        runner = self._runner_thread.runner
        for action in self._hotkeys.drain():
            if action == HotkeyAction.STOP and runner.state != RunnerState.STOPPED:
                self._stop_runner()
            elif action == HotkeyAction.PAUSE:
                if runner.state == RunnerState.RUNNING:
                    self._runner_thread.request_pause()
                    self._pause_btn.setChecked(True)
                elif runner.state == RunnerState.PAUSED:
                    self._runner_thread.request_resume()
                    self._pause_btn.setChecked(False)
            elif action == HotkeyAction.EMERGENCY_STOP and runner.state != RunnerState.STOPPED:
                self._append_log("[EMERGENCY] Hotkey triggered – stopping")
                self._stop_runner()

    # ------------------------------------------------------------------
    # Close handling
    # ------------------------------------------------------------------

    def closeEvent(self, event: QtGui.QCloseEvent | None) -> None:
        if self._modified:
            reply = QtWidgets.QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Save before exiting?",
                QtWidgets.QMessageBox.StandardButton.Save
                | QtWidgets.QMessageBox.StandardButton.Discard
                | QtWidgets.QMessageBox.StandardButton.Cancel,
            )
            if reply == QtWidgets.QMessageBox.StandardButton.Save:
                self._save_preset()
            elif reply == QtWidgets.QMessageBox.StandardButton.Cancel:
                if event is not None:
                    event.ignore()
                return

        if self._runner_thread is not None:
            self._runner_thread.request_stop()
            self._runner_thread.wait(3000)

        self._hotkeys.unregister()
        if event is not None:
            event.accept()


def launch_gui(preset_dir: str | None = None) -> None:
    setup_logging(level=logging.INFO)
    app = QtWidgets.QApplication(sys.argv)
    window = ConfiguratorWindow(initial_preset_dir=preset_dir)
    window.show()
    sys.exit(app.exec())
