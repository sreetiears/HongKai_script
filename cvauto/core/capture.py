"""Screen capture using mss."""

import numpy as np
import cv2
import mss

from .window import get_window_rect


class CaptureEngine:
    """Captures a region of the screen using mss.

    The caller is responsible for providing the target HWND on each capture
    so that moving windows are tracked correctly.
    """

    def __init__(self) -> None:
        self._sct = mss.mss()

    def capture_frame(self, hwnd: int) -> np.ndarray | None:
        """Grab the current client area of *hwnd* and return a BGR image.

        Returns ``None`` if the window is invalid or minimized.
        """
        rect = get_window_rect(hwnd)
        if rect is None:
            return None

        left, top, right, bottom = rect
        width = right - left
        height = bottom - top

        if width <= 0 or height <= 0:
            return None

        monitor = {
            "left": left,
            "top": top,
            "width": width,
            "height": height,
        }

        try:
            img = self._sct.grab(monitor)
        except Exception:
            return None

        arr = np.array(img)
        # mss returns BGRA; OpenCV works natively with BGR.
        arr = cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
        return arr

    def close(self) -> None:
        self._sct.close()
