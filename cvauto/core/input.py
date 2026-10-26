"""Simulated input backend (pyautogui)."""

import pyautogui

# Disable pyautogui's built-in delay between actions.
pyautogui.PAUSE = 0
pyautogui.FAILSAFE = True


class InputBackend:
    """Thin wrapper around pyautogui for clicks, movement, and keys."""

    def move(self, x: int, y: int) -> None:
        pyautogui.moveTo(x, y)

    def click(self, x: int, y: int, button: str = "left") -> None:
        pyautogui.click(x, y, button=button)

    def mouse_down(self, button: str = "left") -> None:
        pyautogui.mouseDown(button=button)

    def mouse_up(self, button: str = "left") -> None:
        pyautogui.mouseUp(button=button)

    def drag(self, x1: int, y1: int, x2: int, y2: int, duration: float = 0.5) -> None:
        pyautogui.moveTo(x1, y1)
        pyautogui.dragTo(x2, y2, duration=duration)

    def press(self, key: str) -> None:
        pyautogui.press(key)

    def scroll(self, amount: int, x: int | None = None, y: int | None = None) -> None:
        if x is not None and y is not None:
            pyautogui.scroll(amount, x=x, y=y)
        else:
            pyautogui.scroll(amount)
