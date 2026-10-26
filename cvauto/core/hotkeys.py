"""Global hotkey controller using the ``keyboard`` library.

Runs in a background thread and communicates with the async runner via
a thread-safe action queue.
"""

from __future__ import annotations

import queue
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable

import keyboard


class HotkeyAction(Enum):
    START = auto()
    STOP = auto()
    PAUSE = auto()
    EMERGENCY_STOP = auto()


@dataclass(frozen=True, slots=True)
class HotkeyConfig:
    start: str = "f9"
    stop: str = "f10"
    pause: str = "f11"
    emergency_stop: str = "ctrl+shift+f12"


class HotkeyController:
    """Registers global hotkeys and exposes a thread-safe action queue."""

    def __init__(self, config: HotkeyConfig | None = None) -> None:
        self.config = config or HotkeyConfig()
        self._actions: queue.Queue[HotkeyAction] = queue.Queue()
        self._registered = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def register(self) -> None:
        """Bind global hotkeys. Idempotent."""
        if self._registered:
            return
        cfg = self.config
        keyboard.add_hotkey(cfg.start, lambda: self._actions.put(HotkeyAction.START))
        keyboard.add_hotkey(cfg.stop, lambda: self._actions.put(HotkeyAction.STOP))
        keyboard.add_hotkey(cfg.pause, lambda: self._actions.put(HotkeyAction.PAUSE))
        keyboard.add_hotkey(
            cfg.emergency_stop,
            lambda: self._actions.put(HotkeyAction.EMERGENCY_STOP),
        )
        self._registered = True

    def unregister(self) -> None:
        """Remove all hotkey bindings."""
        if self._registered:
            keyboard.unhook_all_hotkeys()
            self._registered = False

    # ------------------------------------------------------------------
    # Consumption
    # ------------------------------------------------------------------

    def poll(self) -> HotkeyAction | None:
        """Non-blocking pop of the next pending action."""
        try:
            return self._actions.get_nowait()
        except queue.Empty:
            return None

    def drain(self) -> list[HotkeyAction]:
        """Return all pending actions and clear the queue."""
        actions: list[HotkeyAction] = []
        while True:
            try:
                actions.append(self._actions.get_nowait())
            except queue.Empty:
                break
        return actions

    # ------------------------------------------------------------------
    # Helpers for direct callback binding
    # ------------------------------------------------------------------

    def on_action(self, callback: Callable[[HotkeyAction], None]) -> None:
        """Invoke *callback* synchronously for every action in the queue."""
        for action in self.drain():
            callback(action)
