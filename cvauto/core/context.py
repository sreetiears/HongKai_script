"""Context API exposed to automation scripts."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from .vision import FrameMatches, Match

if TYPE_CHECKING:
    from .preset import Preset
    from .runner import AutomationRunner

logger = logging.getLogger("cvauto.script")


class Context:
    """The sole interface between an automation script and the framework."""

    def __init__(
        self,
        runner: AutomationRunner,
        preset: Preset,
    ) -> None:
        self._runner = runner
        self._preset = preset
        self._landmarks: dict[str, dict] = preset.config.get("landmarks", {})

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._runner.running

    @property
    def paused(self) -> bool:
        return self._runner.paused

    # ------------------------------------------------------------------
    # Frame
    # ------------------------------------------------------------------

    async def next_frame(self) -> FrameMatches:
        """Return the freshest match results.

        If no frame has been processed yet, blocks until the background loop
        produces the first one. Also blocks while the runner is paused.
        """
        await self._runner._wait_unpaused()
        while self._runner.latest_matches is None and self.running:
            await self._runner._wait_unpaused()
            await asyncio.sleep(0.01)
        return self._runner.latest_matches or {}

    def find(self, roi: str, template: str) -> Match | None:
        """Non-blocking lookup of the *current* frame matches.

        Returns ``None`` if the template is not present in the given ROI.
        """
        matches = self._runner.latest_matches or {}
        roi_matches = matches.get(roi, {})
        if template in roi_matches and roi_matches[template]:
            return roi_matches[template][0]
        return None

    async def wait_for(
        self,
        roi: str,
        template: str,
        timeout: float = 5.0,
    ) -> Match:
        """Poll until *template* appears in *roi*, or *timeout* elapses.

        Raises ``TimeoutError`` on expiry.
        """
        start = time.monotonic()
        while self.running:
            await self._runner._wait_unpaused()
            matches = await self.next_frame()
            roi_matches = matches.get(roi, {})
            if template in roi_matches and roi_matches[template]:
                return roi_matches[template][0]
            if time.monotonic() - start > timeout:
                raise TimeoutError(f"Timeout waiting for {template!r} in {roi!r}")
            await asyncio.sleep(0.05)
        raise RuntimeError("Automation stopped while waiting")

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def click(self, target: str | Match | tuple[int, int]) -> None:
        """Click a named landmark, a matched object, or raw coordinates."""
        x: int
        y: int

        if isinstance(target, str):
            landmark = self._landmarks.get(target)
            if landmark is None:
                raise KeyError(f"Unknown landmark: {target!r}")
            x = landmark["x"]
            y = landmark["y"]
        elif isinstance(target, Match):
            x, y = target.center
        elif isinstance(target, (tuple, list)) and len(target) == 2:
            x, y = target  # type: ignore[misc]
        else:
            raise TypeError(f"Invalid click target: {target!r}")

        self._runner.input.click(x, y)

    def move(self, x: int, y: int) -> None:
        self._runner.input.move(x, y)

    def drag(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
        duration: float = 0.5,
    ) -> None:
        self._runner.input.drag(start[0], start[1], end[0], end[1], duration=duration)

    def mouse_down(self, button: str = "left") -> None:
        self._runner.input.mouse_down(button)

    def mouse_up(self, button: str = "left") -> None:
        self._runner.input.mouse_up(button)

    def press(self, key: str) -> None:
        self._runner.input.press(key)

    def scroll(self, amount: int, x: int | None = None, y: int | None = None) -> None:
        self._runner.input.scroll(amount, x, y)

    # ------------------------------------------------------------------
    # Timing
    # ------------------------------------------------------------------

    async def sleep(self, seconds: float) -> None:
        await self._runner._wait_unpaused()
        await asyncio.sleep(seconds)

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log(self, message: str, level: str = "info") -> None:
        log_func = getattr(logger, level, logger.info)
        log_func(message)

    # ------------------------------------------------------------------
    # Dynamic config
    # ------------------------------------------------------------------

    def load_template(self, name: str, path: str, threshold: float | None = None) -> None:
        self._runner.matcher.load_template(name, path, threshold)

    def define_roi(
        self,
        name: str,
        rect: tuple[int, int, int, int],
        template_names: list[str] | None = None,
    ) -> None:
        self._runner.matcher.define_roi(name, rect, template_names)
