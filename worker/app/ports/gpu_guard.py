"""Port for the GPU. Spec: specs/09-local-setup.md#6-gb-vram-model-profile"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Protocol, TypeVar

from app.domain.models import GpuStatus

T = TypeVar("T")


class GpuGuard(Protocol):
    def status(self) -> GpuStatus | None:
        """Current GPU state, or None when NVML cannot be read."""
        ...

    def loaded(self, load: Callable[[], T]) -> AbstractContextManager[T]:
        """Holds the GPU lock, loads a model, and unloads it and frees VRAM on exit."""
        ...
