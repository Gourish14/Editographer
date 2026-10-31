"""Subject mattes for text behind the subject.

Spec: specs/05-editing-brain.md#b8-text-and-audio, specs/04-pipeline.md#stages (6)

Finds the subject in the first frame of the text's window (a face, then a point below it for the
body), has SAM 2 follow it through the window, and hands back one matte per frame. No face, no
mask, or a failure gives None and the text simply stays in front.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import structlog

from app.domain.brain.text_rules import TextItem
from app.domain.photo import FocusSource
from app.ports.frames import FrameMedia
from app.ports.photo import SubjectLocator
from app.ports.segmenter import Point, Segmenter

log = structlog.get_logger()

BODY_BELOW_FACE = 1.4  # torso point, in face heights below the face center


class SubjectMatte:
    def __init__(self, frames: FrameMedia, locator: SubjectLocator, segmenter: Segmenter) -> None:
        self._frames = frames
        self._locator = locator
        self._segmenter = segmenter

    def make(self, video: Path, item: TextItem, fps: int, folder: Path) -> Path | None:
        count = round(item.duration * fps)
        source = folder / "frames"
        try:
            found = self._frames.extract_frames(video, item.at, item.duration, fps, source)
            frames = sorted(source.glob("*.png"))[:count]
            points = self._points(frames[0]) if found and frames else None
            masks = self._segmenter.track(frames, points, folder / "masks") if points else ()
        except Exception as error:  # noqa: BLE001 - a missing mask only means text in front
            log.warning("matte.failed", content=item.content, message=str(error))
            masks = ()
        shutil.rmtree(source, ignore_errors=True)
        if not masks:
            return None
        return _padded(masks, count)

    def _points(self, first: Path) -> tuple[Point, ...] | None:
        box = self._locator.locate(first)
        if box.source is not FocusSource.FACE:
            return None
        return (
            (box.center_x, box.center_y),
            (box.center_x, min(0.98, box.center_y + BODY_BELOW_FACE * box.height)),
        )


def _padded(masks: tuple[Path, ...], count: int) -> Path:
    """Exactly `count` mattes: a short list repeats its last one."""
    folder = masks[0].parent
    for number in range(len(masks) + 1, count + 1):
        shutil.copyfile(masks[-1], folder / f"{number:06d}.png")
    return folder
