# Usage Guide

## Creating a New Preset

1. Create a directory: `mkdir presets/my_game`
2. Add template images to `presets/my_game/templates/`.
3. Create `preset.json` with your window title, ROIs, and templates.
4. Create `script.py` with an async `run(ctx)` function.

## Calibrating ROIs

Use the GUI configurator:

```bash
python -m cvauto gui presets/my_game
```

1. Click **Pick…** to select the target window.
2. Go to the **ROIs** tab and click **Add via Calibrator…**.
3. Drag a rectangle on the live screenshot.
4. Enter the ROI name and optional template names.

ROIs are stored as absolute pixels. If you set `calibrated_at` in `preset.json`,
the framework will auto-scale ROIs and landmarks when the game runs at a
different resolution.

## Writing Scripts

Scripts are standard Python files. The only requirement is an async entrypoint
function (default name: `run`).

```python
async def run(ctx):
    ctx.log("Starting automation")
    while ctx.running:
        matches = await ctx.next_frame()

        # Check if a button is visible in the main ROI
        btn = ctx.find("main_ui", "start_button")
        if btn:
            ctx.click(btn)
            await ctx.wait_for("main_ui", "confirm_button")
            ctx.click("confirm_button")

        await ctx.sleep(0.5)
```

### Error Handling

- `ctx.wait_for` raises `TimeoutError` if the template does not appear.
- If the target window closes, the runner **pauses** automatically and resumes
  when the window reappears.
- If the script raises an exception, the runner **stops** and logs the traceback.

## Headless Mode

For running without the GUI (e.g. on a secondary monitor or remotely):

```bash
python -m cvauto run presets/my_game --hotkeys
```

The `--hotkeys` flag enables global keyboard shortcuts so you can stop the
runner even if the terminal is not focused.

## Debug Overlay

In the GUI, click the **Overlay** toggle after starting the runner. A
semi-transparent window will appear on top of the game showing:

- Blue dashed rectangles for each defined ROI.
- Green solid rectangles for each matched template, with confidence scores.

## Template Matching Tips

- Use **PNG** images with clean backgrounds for best results.
- Default threshold is **0.85**. Lower it if you get false negatives; raise it
  if you get false positives.
- Keep template sizes small (≤200×200) for performance.
- If a game has multiple resolutions, capture templates at the resolution you
  use most, or use `calibrated_at` scaling.
