"""Dialog to capture a window and draw ROIs graphically."""

from __future__ import annotations

import cv2
import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets

from cvauto.core.capture import CaptureEngine
from cvauto.core.window import find_window, get_window_rect


class _RoiCanvas(QtWidgets.QLabel):
    """Interactive label that lets the user drag a rectangle over a screenshot."""

    roi_drawn = QtCore.pyqtSignal(int, int, int, int)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self._pixmap: QtGui.QPixmap | None = None
        self._start: QtCore.QPoint | None = None
        self._current: QtCore.QPoint | None = None
        self._drawing = False

    def set_image(self, pixmap: QtGui.QPixmap) -> None:
        self._pixmap = pixmap
        self.setPixmap(pixmap)
        self.setFixedSize(pixmap.size())

    def mousePressEvent(self, event: QtGui.QMouseEvent | None) -> None:
        if event is not None and event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._start = event.pos()
            self._current = event.pos()
            self._drawing = True

    def mouseMoveEvent(self, event: QtGui.QMouseEvent | None) -> None:
        if self._drawing and event is not None:
            self._current = event.pos()
            self._update_overlay()

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent | None) -> None:
        if self._drawing and event is not None and event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._drawing = False
            self._current = event.pos()
            self._update_overlay()
            if self._start is not None:
                x1, y1 = self._start.x(), self._start.y()
                x2, y2 = self._current.x(), self._current.y()
                x = min(x1, x2)
                y = min(y1, y2)
                w = abs(x2 - x1)
                h = abs(y2 - y1)
                if w > 5 and h > 5:
                    self.roi_drawn.emit(x, y, w, h)

    def _update_overlay(self) -> None:
        if self._pixmap is None or self._start is None or self._current is None:
            return
        pixmap = self._pixmap.copy()
        painter = QtGui.QPainter(pixmap)
        pen = QtGui.QPen(QtGui.QColor(255, 0, 0), 2, QtCore.Qt.PenStyle.DashLine)
        painter.setPen(pen)
        x1, y1 = self._start.x(), self._start.y()
        x2, y2 = self._current.x(), self._current.y()
        painter.drawRect(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
        painter.end()
        self.setPixmap(pixmap)


class RoiCalibratorDialog(QtWidgets.QDialog):
    """Capture a window and let the user draw ROIs on it."""

    roi_created = QtCore.pyqtSignal(str, int, int, int, int, list)

    def __init__(self, window_title: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("ROI Calibrator")
        self.setMinimumSize(800, 600)
        self._window_title = window_title
        self._capture = CaptureEngine()

        self._build_ui()
        self._grab_screenshot()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel(f"Window: {self._window_title}"))
        refresh_btn = QtWidgets.QPushButton("Re-capture")
        refresh_btn.clicked.connect(self._grab_screenshot)
        top.addWidget(refresh_btn)
        top.addStretch()
        layout.addLayout(top)

        # Scroll area for potentially large screenshots
        self._scroll = QtWidgets.QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._canvas = _RoiCanvas()
        self._canvas.roi_drawn.connect(self._on_roi_drawn)
        self._scroll.setWidget(self._canvas)
        layout.addWidget(self._scroll)

        help_lbl = QtWidgets.QLabel("Drag on the image to draw a new ROI. Click 'Re-capture' to refresh.")
        layout.addWidget(help_lbl)

        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _grab_screenshot(self) -> None:
        hwnd = find_window(self._window_title)
        if hwnd is None:
            QtWidgets.QMessageBox.warning(self, "Window not found", f"Could not find window: {self._window_title}")
            return

        frame = self._capture.capture_frame(hwnd)
        if frame is None:
            QtWidgets.QMessageBox.warning(self, "Capture failed", "Could not capture the window.")
            return

        # Convert BGR numpy array to QPixmap
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        q_image = QtGui.QImage(rgb.data, w, h, bytes_per_line, QtGui.QImage.Format.Format_RGB888)
        pixmap = QtGui.QPixmap.fromImage(q_image)
        self._canvas.set_image(pixmap)

    def _on_roi_drawn(self, x: int, y: int, w: int, h: int) -> None:
        name, ok = QtWidgets.QInputDialog.getText(self, "New ROI", "ROI name:")
        if not ok or not name.strip():
            return
        templates_text, ok2 = QtWidgets.QInputDialog.getText(
            self,
            "Templates",
            "Comma-separated template names (optional):",
        )
        templates = [t.strip() for t in templates_text.split(",") if t.strip()] if ok2 else []
        self.roi_created.emit(name.strip(), x, y, w, h, templates)
        QtWidgets.QMessageBox.information(self, "ROI Created", f"ROI '{name}' added ({x},{y} {w}x{h})")

    def closeEvent(self, event: QtGui.QCloseEvent | None) -> None:
        self._capture.close()
        if event is not None:
            event.accept()
