"""Ports for photo analysis. Spec: specs/04-pipeline.md#stages (4)"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.domain.photo import DepthSummary, FocusBox


class ImageSizer(Protocol):
    def size(self, image: Path) -> tuple[int, int]:
        """Width and height in pixels after EXIF rotation. Raises AnalysisError if unreadable."""
        ...


class SubjectLocator(Protocol):
    def locate(self, image: Path) -> FocusBox:
        """The largest face, else the most salient region, else the center. Never fails."""
        ...


class DepthEstimator(Protocol):
    def estimate(self, image: Path, map_file: Path) -> DepthSummary:
        """Writes a gray depth map (near is bright, same size as the image) and summarises it."""
        ...
