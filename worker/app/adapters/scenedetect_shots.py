"""Shot detection with PySceneDetect. Spec: specs/04-pipeline.md#stages (3)"""

from __future__ import annotations

from pathlib import Path

from scenedetect import ContentDetector, detect


class SceneDetectShots:
    def detect(self, path: Path) -> tuple[tuple[float, float], ...]:
        scenes = detect(str(path), ContentDetector())
        return tuple((start.get_seconds(), end.get_seconds()) for start, end in scenes)
