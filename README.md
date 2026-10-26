# CVAuto

A general-purpose, OpenCV-based game automation framework for Windows. Write
async Python scripts that see the screen, find templates, and interact with
games via simulated mouse and keyboard input.

## Features

- **Async/await script API** – write linear, readable automation logic instead of callbacks.
- **Directory-based presets** – each preset is a self-contained folder with JSON
  config, Python script, and template images.
- **Resolution-portable** – calibrate ROIs and landmarks at one resolution; the
  framework auto-scales them at runtime.
- **Hybrid coordinate system** – ROI-relative for dynamic targets, named landmarks
  for static UI elements.
- **Real-time debug overlay** – transparent window drawn over the game showing
  ROI boundaries and match results.
- **Global hotkeys** – F9 Start, F10 Stop, F11 Pause/Resume, Ctrl+Shift+F12 Emergency Stop.
- **GUI Configurator** – PyQt6 editor for presets with window picker, ROI calibrator,
  and template management.

## Quick Start

### Installation

```bash
pip install -e .
```

Requires Python ≥3.10 on Windows (uses `pywin32` and `mss`).

### Run a preset (headless)

```bash
python -m cvauto run presets/aventurine --hotkeys
```

### Open the GUI configurator

```bash
python -m cvauto gui presets/aventurine
```

## Preset Structure

```
presets/my_preset/
├── preset.json          # Templates, ROIs, landmarks, settings
├── script.py            # Async entrypoint
└── templates/
    ├── icon_1.png
    └── icon_2.png
```

### `preset.json` example

```json
{
  "window_title": "My Game",
  "fps_limit": 10,
  "calibrated_at": {"width": 1920, "height": 1080},
  "script": "script.py",
  "entrypoint": "run",
  "templates": [
    {"name": "button", "image_path": "button.png", "threshold": 0.85}
  ],
  "rois": [
    {"label": "main_menu", "rect": {"x": 100, "y": 200, "w": 300, "h": 400}, "template_names": ["button"]}
  ],
  "landmarks": {
    "close_button": {"x": 1900, "y": 20}
  }
}
```

### `script.py` example

```python
async def run(ctx):
    while ctx.running:
        matches = await ctx.next_frame()
        if ctx.find("main_menu", "button"):
            ctx.click("close_button")
        await ctx.sleep(0.5)
```

## Context API Reference

| Method | Description |
|--------|-------------|
| `await ctx.next_frame()` | Get the latest `FrameMatches` dict. |
| `ctx.find(roi, template)` | Non-blocking lookup; returns `Match` or `None`. |
| `await ctx.wait_for(roi, template, timeout=5.0)` | Block until match appears. |
| `ctx.click(target)` | Click a landmark name, `Match`, or `(x, y)` tuple. |
| `ctx.move(x, y)` | Move cursor. |
| `ctx.drag(start, end, duration=0.5)` | Drag between two points. |
| `ctx.press(key)` | Press a keyboard key. |
| `ctx.scroll(amount, x, y)` | Scroll wheel. |
| `await ctx.sleep(seconds)` | Async sleep (respects pause). |
| `ctx.log(msg, level="info")` | Log a message. |
| `ctx.load_template(name, path, threshold)` | Add a template at runtime. |
| `ctx.define_roi(name, rect, templates)` | Add an ROI at runtime. |

## Global Hotkeys

| Key | Action |
|-----|--------|
| `F9` | Start runner |
| `F10` | Stop runner |
| `F11` | Pause / Resume |
| `Ctrl+Shift+F12` | Emergency stop |

## Project Structure

```
cvauto/
├── core/          # Framework engine (capture, vision, input, runner)
├── gui/           # PyQt6 configurator, overlay, ROI calibrator
└── __main__.py    # CLI entry point

presets/
└── aventurine/    # Example ported preset

docs/
├── adr/           # Architecture Decision Records
└── agents/        # Agent docs
```

## License

MIT
