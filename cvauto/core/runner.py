"""Async runner: wires capture, vision, input, and the user script together."""

from __future__ import annotations

import asyncio
import importlib.util
import queue
import sys
import time
import traceback
from pathlib import Path

from .capture import CaptureEngine
from .context import Context
from .input import InputBackend
from .preset import Preset
from .state import RunnerState
from .vision import FrameMatches, Matcher
from .window import find_window, get_window_rect


class AutomationRunner:
    """Loads a preset, starts background capture, and runs the automation script.

    Supports three states:
      * RUNNING – capture + script are active.
      * PAUSED  – capture continues but the script blocks at await points.
      * STOPPED – nothing is running.
    """

    def __init__(self, preset: Preset) -> None:
        self.preset = preset
        self.state = RunnerState.STOPPED
        self.latest_matches: FrameMatches | None = None
        self.last_frame_time: float = 0.0
        self.script_error: Exception | None = None

        self.capture = CaptureEngine()
        self.matcher = Matcher()
        self.input = InputBackend()
        self._ctx: Context | None = None
        self._bg_task: asyncio.Task | None = None
        self._hwnd: int | None = None
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # not paused initially
        self._control_queue: queue.Queue[str] = queue.Queue()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def running(self) -> bool:
        """True while RUNNING or PAUSED (scripts should keep their loops alive)."""
        return self.state in (RunnerState.RUNNING, RunnerState.PAUSED)

    @property
    def paused(self) -> bool:
        return self.state == RunnerState.PAUSED

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Find window, load preset, start background loop, and run script."""
        if self.state != RunnerState.STOPPED:
            raise RuntimeError("Runner is not stopped; call stop() first.")

        self.script_error = None
        self._hwnd = self._resolve_window()
        self._load_preset_assets()
        self._ctx = Context(runner=self, preset=self.preset)

        fps_limit = self.preset.config.get("fps_limit", 10)
        self.state = RunnerState.RUNNING
        self._pause_event.set()
        self._bg_task = asyncio.create_task(self._bg_loop(fps_limit))

        try:
            await self._run_script()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self.script_error = exc
            traceback.print_exc()
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Cancel background capture and clean up."""
        self.state = RunnerState.STOPPED
        self._pause_event.set()  # unblock anything waiting on pause
        if self._bg_task is not None:
            self._bg_task.cancel()
            try:
                await self._bg_task
            except asyncio.CancelledError:
                pass
            self._bg_task = None
        self.capture.close()

    async def pause(self) -> None:
        """Pause script execution (capture continues)."""
        if self.state == RunnerState.RUNNING:
            self.state = RunnerState.PAUSED
            self._pause_event.clear()

    async def resume(self) -> None:
        """Resume a paused script."""
        if self.state == RunnerState.PAUSED:
            self.state = RunnerState.RUNNING
            self._pause_event.set()

    # ------------------------------------------------------------------
    # Thread-safe control requests (safe to call from any thread)
    # ------------------------------------------------------------------

    def request_stop(self) -> None:
        """Request the runner to stop."""
        self._control_queue.put("stop")

    def request_pause(self) -> None:
        """Request the runner to pause."""
        self._control_queue.put("pause")

    def request_resume(self) -> None:
        """Request the runner to resume."""
        self._control_queue.put("resume")

    async def _process_control_queue(self) -> None:
        """Drain pending control requests."""
        while True:
            try:
                action = self._control_queue.get_nowait()
            except queue.Empty:
                break
            if action == "stop":
                await self.stop()
            elif action == "pause":
                await self.pause()
            elif action == "resume":
                await self.resume()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _wait_unpaused(self) -> None:
        """Block until the runner is no longer paused."""
        await self._pause_event.wait()

    def _resolve_window(self) -> int:
        """Locate the target window by substring match."""
        title = self.preset.config.get("window_title", "")
        hwnd = find_window(title)
        if hwnd is None:
            raise RuntimeError(f"Target window not found: {title!r}")
        return hwnd

    def _load_preset_assets(self) -> None:
        """Load templates and ROIs, scaling ROIs/landmarks if needed."""
        # --- templates -------------------------------------------------
        template_dir = Path(self.preset.template_dir)
        for tmpl in self.preset.config.get("templates", []):
            path = template_dir / tmpl["image_path"]
            self.matcher.load_template(
                tmpl["name"],
                str(path),
                tmpl.get("threshold"),
            )

        # --- scaling factors -------------------------------------------
        calib = self.preset.config.get("calibrated_at", {})
        calib_w = calib.get("width")
        calib_h = calib.get("height")

        rect = get_window_rect(self._hwnd)  # type: ignore[arg-type]
        actual_w = rect[2] - rect[0]
        actual_h = rect[3] - rect[1]

        scale_x = scale_y = 1.0
        if calib_w and calib_h and calib_w > 0 and calib_h > 0:
            scale_x = actual_w / calib_w
            scale_y = actual_h / calib_h

        # --- ROIs ------------------------------------------------------
        for roi in self.preset.config.get("rois", []):
            r = roi["rect"]
            x = int(r["x"] * scale_x)
            y = int(r["y"] * scale_y)
            w = int(r["w"] * scale_x)
            h = int(r["h"] * scale_y)
            self.matcher.define_roi(
                roi["label"],
                (x, y, w, h),
                roi.get("template_names"),
            )

        # --- landmarks -------------------------------------------------
        landmarks = self.preset.config.get("landmarks", {})
        scaled_landmarks: dict[str, dict] = {}
        for name, point in landmarks.items():
            scaled_landmarks[name] = {
                "x": int(point["x"] * scale_x),
                "y": int(point["y"] * scale_y),
            }
        self.preset.config["landmarks"] = scaled_landmarks

    async def _bg_loop(self, fps_limit: float) -> None:
        """Continuously capture and match while state is RUNNING or PAUSED."""
        while self.running:
            await self._process_control_queue()
            if self.state == RunnerState.STOPPED:
                break
            start = time.monotonic()

            # Detect window closure / minimisation.
            rect = get_window_rect(self._hwnd)  # type: ignore[arg-type]
            if rect is None:
                # Window closed – pause and wait for it to reappear.
                if self.state == RunnerState.RUNNING:
                    await self.pause()
                    self._ctx.log("Window lost – pausing", level="warn")  # type: ignore[union-attr]
                await asyncio.sleep(1.0)
                # Attempt re-acquire
                title = self.preset.config.get("window_title", "")
                new_hwnd = find_window(title)
                if new_hwnd is not None:
                    self._hwnd = new_hwnd
                    self._load_preset_assets()
                    await self.resume()
                    self._ctx.log("Window re-acquired – resuming", level="info")  # type: ignore[union-attr]
                continue

            frame = self.capture.capture_frame(self._hwnd)
            if frame is not None and self.state == RunnerState.RUNNING:
                self.latest_matches = self.matcher.match(frame)
                self.last_frame_time = time.monotonic()

            elapsed = time.monotonic() - start
            sleep_time = max(0.0, 1.0 / fps_limit - elapsed)
            await asyncio.sleep(sleep_time)

    async def _run_script(self) -> None:
        """Import the preset's script and await its entrypoint."""
        preset_dir = Path(self.preset.path)
        script_file = preset_dir / self.preset.config.get("script", "script.py")
        entrypoint = self.preset.config.get("entrypoint", "run")

        module_name = f"cvauto_preset_{self.preset.name}"

        # Temporarily add preset directory to path so imports work.
        sys.path.insert(0, str(preset_dir))
        try:
            spec = importlib.util.spec_from_file_location(module_name, script_file)
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot load script: {script_file}")

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            func = getattr(module, entrypoint, None)
            if func is None:
                raise AttributeError(
                    f"Entrypoint '{entrypoint}' not found in {script_file}"
                )

            await func(self._ctx)
        finally:
            sys.path.remove(str(preset_dir))
