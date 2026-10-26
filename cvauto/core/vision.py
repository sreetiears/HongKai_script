"""Template matching, ROI management, and match data structures."""

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass(frozen=True, slots=True)
class Match:
    """A single template match occurrence inside an ROI."""

    center: tuple[int, int]
    rect: tuple[int, int, int, int]  # x, y, w, h
    confidence: float
    template_name: str
    roi_name: str


FrameMatches = dict[str, dict[str, list[Match]]]


@dataclass
class Template:
    name: str
    image: np.ndarray
    threshold: float
    path: str


@dataclass
class ROI:
    name: str
    rect: tuple[int, int, int, int]  # x, y, w, h
    template_names: list[str]


class Matcher:
    """Manages templates and ROIs and performs template matching per frame."""

    def __init__(self) -> None:
        self.templates: dict[str, Template] = {}
        self.rois: dict[str, ROI] = {}

    def load_template(self, name: str, image_path: str, threshold: float | None = None) -> None:
        """Load a template image from disk."""
        img = cv2.imread(str(image_path))
        if img is None:
            raise ValueError(f"Cannot load template image: {image_path}")

        if threshold is None:
            threshold = 0.85

        self.templates[name] = Template(
            name=name,
            image=img,
            threshold=threshold,
            path=str(image_path),
        )

    def define_roi(self, name: str, rect: tuple[int, int, int, int], template_names: list[str] | None = None) -> None:
        """Define a region of interest."""
        self.rois[name] = ROI(
            name=name,
            rect=rect,
            template_names=template_names or [],
        )

    def match(self, frame: np.ndarray | None) -> FrameMatches:
        """Run template matching for all ROIs and return structured results."""
        if frame is None or frame.size == 0:
            return {}

        frame_h, frame_w = frame.shape[:2]
        results: FrameMatches = {}

        for roi_name, roi in self.rois.items():
            x, y, w, h = roi.rect

            # Clamp to frame bounds
            x = max(0, min(x, frame_w - 1))
            y = max(0, min(y, frame_h - 1))
            w = min(w, frame_w - x)
            h = min(h, frame_h - y)

            if w <= 0 or h <= 0:
                continue

            roi_frame = frame[y : y + h, x : x + w]
            roi_results: dict[str, list[Match]] = {}

            # If ROI specifies templates, only search those; otherwise search all.
            templates_to_search = roi.template_names if roi.template_names else list(self.templates.keys())

            for tmpl_name in templates_to_search:
                tmpl = self.templates.get(tmpl_name)
                if tmpl is None:
                    continue

                th, tw = tmpl.image.shape[:2]
                if roi_frame.shape[0] < th or roi_frame.shape[1] < tw:
                    continue

                found = _match_template_multi(roi_frame, tmpl.image, tmpl.threshold)
                if not found:
                    continue

                matches: list[Match] = []
                for (tx, ty), confidence in found:
                    match = Match(
                        center=(x + tx + tw // 2, y + ty + th // 2),
                        rect=(x + tx, y + ty, tw, th),
                        confidence=confidence,
                        template_name=tmpl_name,
                        roi_name=roi_name,
                    )
                    matches.append(match)

                roi_results[tmpl_name] = matches

            if roi_results:
                results[roi_name] = roi_results

        return results


def _match_template_multi(
    image: np.ndarray,
    template: np.ndarray,
    threshold: float,
) -> list[tuple[tuple[int, int], float]]:
    """Find all non-overlapping template matches above *threshold*.

    Uses cv2.matchTemplate with TM_CCOEFF_NORMED and suppresses overlapping
    detections by blanking out a neighborhood around each found match.
    """
    result = cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED)
    h, w = template.shape[:2]
    matches: list[tuple[tuple[int, int], float]] = []

    while True:
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val < threshold:
            break

        mx, my = max_loc
        matches.append(((mx, my), float(max_val)))

        # Suppress the neighborhood so we don't return overlapping boxes.
        y1 = max(0, my - h // 2)
        y2 = min(result.shape[0], my + h // 2)
        x1 = max(0, mx - w // 2)
        x2 = min(result.shape[1], mx + w // 2)
        result[y1:y2, x1:x2] = -1.0

    return matches
