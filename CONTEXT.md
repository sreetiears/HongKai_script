# CV Automation Framework

A general-purpose OpenCV-based automation framework for driving PC games via visual recognition and simulated input.

## Language

**Preset**:
A saved configuration bundle for automating a specific game or mini-game. Contains the window target, templates, ROIs, thresholds, and a reference to the automation script.
_Avoid_: Profile, config, setting

**Template**:
A small reference image file used by the framework to locate UI elements or game objects within a captured frame. Registered in a preset with a name and similarity threshold.
_Avoid_: Asset, image, sprite

**ROI (Region of Interest)**:
A defined rectangular sub-region of the target window where the framework searches for specific templates. Presets name their ROIs so automation scripts can reference match results symbolically.
_Avoid_: Region, area, zone

**Match**:
A single detected occurrence of a template inside an ROI within one captured frame, including its bounding rectangle, center point, and confidence score.
_Avoid_: Detection, result, hit

**Automation script**:
The user-defined async logic that receives per-frame match data and issues input commands via the framework's context API.
_Avoid_: Bot, macro, plugin

**Window target**:
The specific OS application window that the framework captures frames from and sends input to.
_Avoid_: Game, process, target

**Calibration resolution**:
The window size (in pixels) at which a preset's absolute ROI coordinates were originally measured. The framework uses this to auto-scale ROIs when the target window is a different size.
_Avoid_: Reference resolution, base resolution, design resolution
