"""Photo analysis use case. Spec: specs/04-pipeline.md#stages (4)

Returns a pure result. The caller stores it and picks the slot (B4: photos fill at most 30% of
slots and never a drop, see `app.domain.photo.photo_allowed`).
"""

from __future__ import annotations

from pathlib import Path

import structlog

from app.domain.errors import AnalysisError
from app.domain.photo import PhotoAnalysis, choose_motion
from app.ports.photo import DepthEstimator, ImageSizer, SubjectLocator

log = structlog.get_logger()


class AnalyzePhoto:
    def __init__(self, sizer: ImageSizer, locator: SubjectLocator, depth: DepthEstimator) -> None:
        self._sizer = sizer
        self._locator = locator
        self._depth = depth

    def run(self, image: Path, depth_map_file: Path) -> PhotoAnalysis:
        if not image.is_file():
            raise AnalysisError(f"Could not open {image.name}")
        width, height = self._sizer.size(image)
        focus = self._locator.locate(image)
        depth = self._depth.estimate(image, depth_map_file)
        motion = choose_motion(depth)
        log.info(
            "photo.analyzed",
            file=image.name,
            focus=focus.source.value,
            contrast=round(depth.contrast, 3),
            motion=motion.value,
        )
        return PhotoAnalysis(width, height, focus, motion, depth)
