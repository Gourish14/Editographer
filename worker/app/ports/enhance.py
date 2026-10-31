"""Ports for frame interpolation and upscaling.

Spec: specs/04-pipeline.md#stages (6, 7), specs/09-local-setup.md#6-gb-vram-model-profile

A session keeps one model on the GPU for a whole batch and holds the GPU until it closes, so a
job opens one session per stage and checks for cancellation between frames.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

Frame = NDArray[np.uint8] | NDArray[np.uint16]
"""Height x width x 3, RGB. Output frames keep the bit depth of the input."""


@dataclass(frozen=True)
class FrameSize:
    width: int
    height: int


class InterpolationSession(Protocol):
    def between(self, first: Frame, second: Frame, time: float = 0.5) -> Frame:
        """The frame at time, strictly between 0 (first) and 1 (second)."""
        ...

    def between_files(self, first: Path, second: Path, target: Path, time: float = 0.5) -> None:
        """Same as between, from image files to an image file."""
        ...


class UpscaleSession(Protocol):
    def upscale(self, frame: Frame, size: FrameSize) -> Frame:
        """The frame at exactly this size."""
        ...

    def upscale_file(self, source: Path, target: Path, size: FrameSize) -> None:
        """Same as upscale, from an image file to an image file."""
        ...


class Interpolator(Protocol):
    def session(self) -> AbstractContextManager[InterpolationSession]: ...


class Upscaler(Protocol):
    def session(self, cool_mode: bool = False) -> AbstractContextManager[UpscaleSession]:
        """Cool mode trades speed for a lower GPU load."""
        ...
