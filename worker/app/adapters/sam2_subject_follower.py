"""Follows a picked subject through a 360 clip with SAM 2.1 small.

Spec: specs/08-osmo360.md (rule 5, subject follow and picker), specs/05-editing-brain.md#b7

SAM 2 does not run on the equirect frame: a person there is under 1% of the pixels, stretched,
and cut in two at the frame edge when they cross the seam. Instead it runs on a 100 degree
rectilinear view centered on the subject (`equirect_view`), in chunks of CHUNK_SEC. Each chunk
starts with the view re-centered on where the previous chunk ended and the subject prompted at
the view center, so the subject can travel any distance and cross the 0/360 seam. The mask center
is mapped back to an equirect position. Forward and backward from the tap time are separate runs.
The segmenter loads SAM 2 through the GPU guard once per chunk, so only one model is ever on
the GPU. The subject is lost when a chunk finds no subject or a mask empties.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import structlog

from app.adapters.equirect_view import centered_on, view_maps, view_point_to_equirect
from app.adapters.opencv_photo import read_image
from app.domain.models import FollowPoint
from app.domain.shots import SubjectSample
from app.ports.frames import FrameMedia
from app.ports.segmenter import Segmenter
from app.ports.subject_follow import FollowTrack

log = structlog.get_logger()

TRACK_FPS = 4.0  # the same rate as the analysis subject track
CHUNK_SEC = 2.0
EQUIRECT_WIDTH = 2048
VIEW_SIZE = 640
VIEW_FOV = 100.0
MIN_MASK_SHARE = 0.002
CENTER = (0.5, 0.5)
STEP = 1.0 / TRACK_FPS


class Sam2SubjectFollower:
    def __init__(self, frames: FrameMedia, segmenter: Segmenter) -> None:
        self._frames = frames
        self._segmenter = segmenter

    def follow(
        self, video: Path, point: FollowPoint, start: float, end: float, folder: Path
    ) -> FollowTrack:
        tap = min(max(point.time_sec, start), end)
        try:
            forward, lost_after = self._run(video, point, tap, end, 1, folder)
            backward, lost_before = self._run(video, point, tap, start, -1, folder)
        finally:
            shutil.rmtree(folder, ignore_errors=True)
        merged = {sample.time: sample for sample in (*backward, *forward)}
        samples = tuple(merged[time] for time in sorted(merged))
        lost = tuple(time for time in (lost_before, lost_after) if time is not None)
        return FollowTrack(samples, lost)

    def _run(
        self, video: Path, point: FollowPoint, tap: float, limit: float, way: int, folder: Path
    ) -> tuple[list[SubjectSample], float | None]:
        """One direction from the tap: samples in walking order, and where the subject was lost."""
        samples: list[SubjectSample] = []
        x, y = point.x, point.y
        time = tap
        first = True
        while True:
            remaining = (limit - time) * way
            if not first and remaining < STEP / 2:
                break
            span = max(0.0, min(CHUNK_SEC, remaining))
            found, lost = self._chunk(
                video,
                x,
                y,
                time,
                span,
                way,
                folder / f"{'fwd' if way > 0 else 'back'}{len(samples)}",
            )
            samples.extend(found if first else found[1:])
            if lost is not None:
                return samples, lost
            if len(found) <= 1:
                break
            x, y, time = found[-1].x, found[-1].y, found[-1].time
            first = False
        return samples, None

    def _chunk(
        self, video: Path, x: float, y: float, time: float, span: float, way: int, folder: Path
    ) -> tuple[list[SubjectSample], float | None]:
        """Samples at `time` and then each step toward `time + way * span`, centered on (x, y).

        The second value is the source time the subject was lost, None when it was followed to
        the end of the chunk.
        """
        start = time if way > 0 else time - span
        raw = folder / "equirect"
        self._frames.extract_frames(
            video, max(0.0, start), span + STEP / 4, TRACK_FPS, raw, EQUIRECT_WIDTH
        )
        files = sorted(raw.glob("*.png"))
        if not files:
            return [], time
        files = files if way > 0 else files[::-1]
        yaw, pitch = centered_on(x, y)
        views = _render_views(files, folder / "views", yaw, pitch)
        masks = self._segmenter.track(views, [CENTER], folder / "masks")
        if not masks:
            return [], time
        found: list[SubjectSample] = []
        for index, mask in enumerate(masks):
            sample_time = round(time + way * index * STEP, 4)
            center = _mask_center(mask)
            if center is None:
                return found, sample_time
            ex, ey = view_point_to_equirect(*center, VIEW_SIZE, VIEW_FOV, yaw, pitch)
            found.append(SubjectSample(time=sample_time, x=round(ex, 5), y=round(ey, 5)))
        return found, None


def _render_views(files: list[Path], folder: Path, yaw: float, pitch: float) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    maps: tuple[Any, Any] | None = None
    views = []
    for index, file in enumerate(files, start=1):
        image = read_image(file)
        if maps is None:
            height, width = image.shape[:2]
            maps = view_maps(width, height, VIEW_SIZE, VIEW_FOV, yaw, pitch)
        view = cv2.remap(image, maps[0], maps[1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
        path = folder / f"{index:06d}.png"
        cv2.imwrite(str(path), view)
        views.append(path)
    return views


def _mask_center(mask: Path) -> tuple[float, float] | None:
    pixels = cv2.imread(str(mask), cv2.IMREAD_GRAYSCALE)
    if pixels is None:
        return None
    rows, columns = np.nonzero(pixels > 127)
    if rows.size < MIN_MASK_SHARE * pixels.size:
        return None
    return float(columns.mean()) + 0.5, float(rows.mean()) + 0.5
