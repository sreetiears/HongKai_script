"""Window discovery and geometry."""

import win32gui


def find_window(title_substring: str) -> int | None:
    """Find the first visible window whose title contains the given substring.

    Returns the HWND (window handle) or None if no match is found.
    """
    result = None

    def callback(hwnd: int, substr: str) -> bool:
        nonlocal result
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if substr.lower() in title.lower():
                result = hwnd
                return False  # stop enumeration
        return True  # continue

    win32gui.EnumWindows(callback, title_substring)
    return result


def list_windows() -> list[tuple[int, str]]:
    """Return a list of all visible top-level windows as (hwnd, title)."""
    results: list[tuple[int, str]] = []

    def callback(hwnd: int, _: object) -> bool:
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title:
                results.append((hwnd, title))
        return True

    win32gui.EnumWindows(callback, None)
    return results


def get_window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    """Return (left, top, right, bottom) for the given HWND.

    Returns None if the window no longer exists.
    """
    try:
        return win32gui.GetWindowRect(hwnd)
    except Exception:
        return None


def is_window_valid(hwnd: int | None) -> bool:
    """Return True if the HWND still points to a visible window."""
    if hwnd is None:
        return False
    try:
        return bool(win32gui.IsWindow(hwnd) and win32gui.IsWindowVisible(hwnd))
    except Exception:
        return False
