"""Preset loading and validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class PresetError(Exception):
    """Base class for preset-related errors."""


class MissingTemplateError(PresetError):
    """Raised when a declared template image does not exist on disk."""

    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"Template not found: {path}")


class MissingScriptError(PresetError):
    """Raised when the automation script file is missing."""


class InvalidPresetError(PresetError):
    """Raised when preset.json is malformed or missing required fields."""


@dataclass
class Preset:
    """A loaded preset directory."""

    name: str
    path: str
    config: dict
    template_dir: str


def load_preset(preset_dir: str) -> Preset:
    """Load and validate a preset directory.

    Raises
    ------
    FileNotFoundError
        If preset.json does not exist.
    InvalidPresetError
        If preset.json cannot be parsed.
    MissingScriptError
        If the referenced script file is missing.
    MissingTemplateError
        If any declared template image is missing.
    """
    preset_dir_path = Path(preset_dir)
    config_path = preset_dir_path / "preset.json"

    if not config_path.exists():
        raise FileNotFoundError(f"No preset.json found in {preset_dir}")

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as exc:
        raise InvalidPresetError(f"Invalid JSON in preset.json: {exc}")

    if not isinstance(config, dict):
        raise InvalidPresetError("preset.json must contain a JSON object")

    templates_dir = preset_dir_path / "templates"
    script_path = preset_dir_path / config.get("script", "script.py")

    if not script_path.exists():
        raise MissingScriptError(f"Script not found: {script_path}")

    # Validate that every declared template image exists.
    for tmpl in config.get("templates", []):
        if not isinstance(tmpl, dict):
            raise InvalidPresetError("Each template entry must be an object")
        img_path = templates_dir / tmpl.get("image_path", "")
        if not img_path.exists():
            raise MissingTemplateError(img_path)

    return Preset(
        name=preset_dir_path.name,
        path=str(preset_dir_path),
        config=config,
        template_dir=str(templates_dir),
    )
