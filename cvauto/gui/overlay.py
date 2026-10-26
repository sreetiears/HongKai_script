"""Transparent debug overlay that draws ROIs and matches on top of the target window."""

from __future__ import annotations

import time

import win32gui
from PyQt6 import QtCore, QtGui, QtWidgets

from cvauto.core.state import RunnerState
from cvauto.core.window import get_window_rect


class OverlayWindow(QtWidgets.QWidget):
    """Frameless, transparent, click-through overlay window.

    Polls the target window position and draws rectangles for ROIs and
    template matches.
    """

    def __init__(self, runner: object, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = runner
        self._enabled = True

        self.setWindowFlags(
            QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
            | QtCore.Qt.WindowType.Tool
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating)

        # Update timer ~30 FPS
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._update)
        self._timer.start(33)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def toggle(self) -> None:
        self._enabled = not self._enabled
        self.setVisible(self._enabled)

    @property
    def overlay_enabled(self) -> bool:
        return self._enabled

    # ------------------------------------------------------------------
    # Update loop
    # ------------------------------------------------------------------

    def _update(self) -> None:
        if not self._enabled:
            if self.isVisible():
                self.hide()
            return

        hwnd = getattr(self._runner, "_hwnd", None)
        if hwnd is None:
            self.hide()
            return

        rect = get_window_rect(hwnd)
        if rect is None:
            self.hide()
            return

        left, top, right, bottom = rect
        self.setGeometry(left, top, right - left, bottom - top)
        if not self.isVisible():
            self.show()
        self.update()

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event: QtGui.QPaintEvent | None) -> None:  # noqa: ARG002
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        # Draw ROI rectangles (blue, dashed)
        pen_roi = QtGui.QPen(QtGui.QColor(0, 150, 255, 200), 2)
        pen_roi.setStyle(QtCore.Qt.PenStyle.DashLine)
        painter.setPen(pen_roi)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)

        matcher = getattr(self._runner, "matcher", None)
        if matcher is not None:
            for roi in matcher.rois.values():
                x, y, w, h = roi.rect
                painter.drawRect(x, y, w, h)
                painter.drawText(x + 4, y + 14, roi.name)

        # Draw match rectangles (green, solid) + confidence
        pen_match = QtGui.QPen(QtGui.QColor(0, 255, 100, 220), 2)
        painter.setPen(pen_match)

        matches = getattr(self._runner, "latest_matches", None) or {}
        for roi_name, tmpl_dict in matches.items():
            for tmpl_name, match_list in tmpl_dict.items():
                for match in match_list:
                    x, y, w, h = match.rect
                    painter.drawRect(x, y, w, h)
                    text = f"{tmpl_name} ({match.confidence:.2f})"
                    painter.drawText(x + 4, y + 14, text)

        painter.end()
