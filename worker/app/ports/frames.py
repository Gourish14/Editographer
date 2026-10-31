"""Ports for work on single frames. Spec: specs/04-pipeline.md#stages (6, 7)"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.ports.enhance import FrameSize


@dataclass(frozen=True)
class UpscaleSpec:
    """One upscaled video: where from and to, the sizes, the frames and the encode."""

    source: Path
    target: Path
    source_size: FrameSize
    size: FrameSize
    frames: int
    fps: int
    quality: int
    preset: str
    cool_mode: bool


class FrameMedia(Protocol):
    def extract_frames(
        self, source: Path, start: float, duration: float, fps: float, folder: Path
    ) -> int:
        """Writes the window as 1-based `%06d.png` at this frame rate and returns how many."""
        ...


class VideoUpscaler(Protocol):
    def upscale_video(self, spec: UpscaleSpec, on_frame: Callable[[int], None]) -> None:
        """Writes exactly `spec.frames` frames at `spec.size`; `on_frame(done)` runs after each.

        An exception from `on_frame`, such as a cancellation, stops the work and propagates.
        """
        ...
