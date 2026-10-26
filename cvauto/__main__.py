"""CLI entry point.

Examples
--------
    python -m cvauto run presets/aventurine
    python -m cvauto run presets/aventurine --hotkeys
    python -m cvauto gui presets/aventurine
"""

from __future__ import annotations

import argparse
import asyncio

from cvauto.core.hotkeys import HotkeyAction, HotkeyController
from cvauto.core.logging_config import setup_logging
from cvauto.core.preset import load_preset
from cvauto.core.runner import AutomationRunner
from cvauto.core.state import RunnerState


async def _hotkey_poller(runner: AutomationRunner, hotkeys: HotkeyController) -> None:
    """Background task that consumes hotkey actions and drives the runner."""
    while True:
        action = hotkeys.poll()
        if action == HotkeyAction.START and runner.state == RunnerState.STOPPED:
            asyncio.create_task(runner.start())
        elif action == HotkeyAction.STOP and runner.state != RunnerState.STOPPED:
            await runner.stop()
        elif action == HotkeyAction.PAUSE:
            if runner.state == RunnerState.RUNNING:
                await runner.pause()
            elif runner.state == RunnerState.PAUSED:
                await runner.resume()
        elif action == HotkeyAction.EMERGENCY_STOP and runner.state != RunnerState.STOPPED:
            print("[EMERGENCY] Stopping immediately")
            await runner.stop()
        await asyncio.sleep(0.1)


async def run_preset(preset_dir: str, *, with_hotkeys: bool = False) -> None:
    preset = load_preset(preset_dir)
    runner = AutomationRunner(preset)
    hotkeys = HotkeyController()

    poller_task: asyncio.Task | None = None
    if with_hotkeys:
        hotkeys.register()
        poller_task = asyncio.create_task(_hotkey_poller(runner, hotkeys))
        print("Hotkeys registered:  F9=Start  F10=Stop  F11=Pause  Ctrl+Shift+F12=Emergency Stop")

    try:
        await runner.start()
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"[ERROR] {e}")
        raise
    finally:
        if runner.state != RunnerState.STOPPED:
            await runner.stop()
        if poller_task is not None:
            poller_task.cancel()
            try:
                await poller_task
            except asyncio.CancelledError:
                pass
        hotkeys.unregister()


def main() -> None:
    parser = argparse.ArgumentParser(description="CV Automation Framework")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Console logging level",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run -----------------------------------------------------------------
    run_parser = subparsers.add_parser("run", help="Run a preset in headless mode")
    run_parser.add_argument("preset", help="Path to preset directory")
    run_parser.add_argument(
        "--hotkeys",
        action="store_true",
        help="Enable global hotkeys (F9=Start, F10=Stop, F11=Pause)",
    )

    # gui -----------------------------------------------------------------
    gui_parser = subparsers.add_parser("gui", help="Open the GUI configurator")
    gui_parser.add_argument("preset", nargs="?", help="Optional preset to preload")

    args = parser.parse_args()

    import logging

    setup_logging(level=getattr(logging, args.log_level))

    if args.command == "run":
        asyncio.run(run_preset(args.preset, with_hotkeys=args.hotkeys))
    elif args.command == "gui":
        from cvauto.gui.configurator import launch_gui

        launch_gui(args.preset)


if __name__ == "__main__":
    main()
