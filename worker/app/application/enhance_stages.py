"""The GPU stages of a render: RIFE slow motion and Real-ESRGAN upscaling.

Spec: specs/04-pipeline.md#stages (6, 7), specs/09-local-setup.md#cool-mode

Each stage opens one model session, checks for cancellation between frames and, in cool mode,
rests before the stage and checks the temperature between segments and every few frames.
"""

from __future__ import annotations

import math
import shutil
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import structlog

from app.application.cool_mode import CoolDown
from app.application.job_runner import CancellationToken
from app.domain.brain.ramps import (
    INTERPOLATE_RIFE,
    curve_source_length,
    source_time_at,
    speed_at,
)
from app.domain.brain.reframe import FrameSize as CropSize
from app.domain.brain.reframe import base_fov, crop_size, ratio_value, view_pixel_width
from app.domain.models import AssetInput
from app.domain.plan import EditPlan, Segment
from app.ports.enhance import InterpolationSession, Interpolator
from app.ports.frames import FrameMedia, UpscaleSpec, VideoUpscaler

log = structlog.get_logger()

RETIME_FOLDER = "retime"
FRAME_PATTERN = "%06d.png"
SOURCE_MARGIN_FRAMES = 2
WHOLE_FRAME_EPSILON = 0.02
SLOW_BELOW = 0.99
COOL_CHECK_EVERY_FRAMES = 10
VIDEO_360 = "video360"
MIN_UPSCALE_FACTOR = 1.15


def needs_rife(segment: Segment) -> bool:
    return segment.speed.interpolate == INTERPOLATE_RIFE and len(segment.speed.curve) > 2


class RetimeStage:
    """Writes the frames of every RIFE ramp, on the segment's own timeline, before composing."""

    def __init__(
        self, interpolator: Interpolator, media: FrameMedia, cool_down: CoolDown | None = None
    ) -> None:
        self._interpolator = interpolator
        self._media = media
        self._cool_down = cool_down

    def run(
        self,
        segments: Sequence[tuple[Segment, Path, int]],
        fps: int,
        work: Path,
        token: CancellationToken,
        on_segment: Callable[[int, int], None] = lambda done, total: None,
    ) -> dict[str, Path]:
        """`segments` are (segment, source file, frame count). Returns frame patterns by id."""
        patterns: dict[str, Path] = {}
        if not segments:
            return patterns
        if self._cool_down:
            self._cool_down.stage_pause()
        with self._interpolator.session() as session:
            for done, (segment, source, frames) in enumerate(segments, start=1):
                token.raise_if_cancelled()
                if self._cool_down and done > 1:
                    self._cool_down.wait_until_cool()
                folder = work / RETIME_FOLDER / segment.id
                self._retime(session, segment, source, frames, fps, folder, token)
                patterns[segment.id] = folder / "out" / FRAME_PATTERN
                on_segment(done, len(segments))
        return patterns

    def _retime(
        self,
        session: InterpolationSession,
        segment: Segment,
        source: Path,
        frames: int,
        fps: int,
        folder: Path,
        token: CancellationToken,
    ) -> None:
        native = segment.source.native_fps or float(fps)
        curve, duration = segment.speed.curve, segment.duration
        window = curve_source_length(curve, duration) + SOURCE_MARGIN_FRAMES / native
        shutil.rmtree(folder, ignore_errors=True)
        available = self._media.extract_frames(
            source, segment.src_in, window, native, folder / "in"
        )
        (folder / "out").mkdir(parents=True, exist_ok=True)
        for frame in range(frames):
            token.raise_if_cancelled()
            time = min(frame / fps, duration)
            position = source_time_at(curve, duration, time) * native
            index = min(int(position), available - 1)
            fraction = position - index
            target = folder / "out" / (FRAME_PATTERN % (frame + 1))
            slow = speed_at(curve, time / duration) < SLOW_BELOW
            if slow and fraction > WHOLE_FRAME_EPSILON and index + 1 < available:
                session.between_files(
                    folder / "in" / (FRAME_PATTERN % (index + 1)),
                    folder / "in" / (FRAME_PATTERN % (index + 2)),
                    target,
                    fraction,
                )
            else:
                nearest = min(round(position), available - 1)
                shutil.copyfile(folder / "in" / (FRAME_PATTERN % (nearest + 1)), target)
        shutil.rmtree(folder / "in", ignore_errors=True)


class UpscaleStage:
    """Upscales the joined edit to the output size, resting first in cool mode."""

    def __init__(self, upscaler: VideoUpscaler, cool_down: CoolDown | None = None) -> None:
        self._upscaler = upscaler
        self._cool_down = cool_down

    def run(
        self,
        spec: UpscaleSpec,
        token: CancellationToken,
        on_progress: Callable[[int, int], None],
    ) -> None:
        if self._cool_down:
            self._cool_down.stage_pause()

        def on_frame(done: int) -> None:
            token.raise_if_cancelled()
            if self._cool_down and done % COOL_CHECK_EVERY_FRAMES == 0:
                self._cool_down.wait_until_cool()
            on_progress(done, spec.frames)

        self._upscaler.upscale_video(spec, on_frame)


@dataclass(frozen=True)
class WorkingSize:
    """The size an edit is composed at, and whether upscaling must reach the output size."""

    width: int
    height: int
    upscale: bool


def working_size(plan: EditPlan, assets: Mapping[str, AssetInput]) -> WorkingSize:
    """Spec 04 stage 6: in Max quality, the largest size the sources really hold, up to the output.

    Flat clips hold their crop window; a 360 view holds source width x FOV / 360 (spec 08 rule 8).
    """
    output = plan.output
    held = 0.0
    for segment in plan.segments:
        asset = assets.get(segment.asset_id)
        if asset is None or not asset.width or not asset.height:
            continue
        held = max(held, _held_width(segment, asset, output.ratio))
    if held <= 0:
        return WorkingSize(output.width, output.height, False)
    factor = output.width / held
    if factor < MIN_UPSCALE_FACTOR:
        return WorkingSize(output.width, output.height, False)
    width = _even(held)
    return WorkingSize(width, _even(width * output.height / output.width), True)


def _held_width(segment: Segment, asset: AssetInput, ratio: str) -> float:
    assert asset.width and asset.height
    if segment.type == VIDEO_360:
        return view_pixel_width(asset.width, base_fov(ratio))
    window_width, _ = crop_size(CropSize(asset.width, asset.height), ratio_value(ratio))
    return window_width


def _even(value: float) -> int:
    return max(2, math.floor(value / 2) * 2)
