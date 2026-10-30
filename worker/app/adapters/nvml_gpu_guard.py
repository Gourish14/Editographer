"""GPU lock and NVML status. Spec: specs/09-local-setup.md#6-gb-vram-model-profile"""

from __future__ import annotations

import gc
import importlib
import threading
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import TypeVar

import pynvml
import structlog

from app.domain.models import GpuStatus

T = TypeVar("T")

log = structlog.get_logger()
BYTES_PER_MB = 1024 * 1024


def _empty_torch_cache() -> None:
    """Frees VRAM. torch is imported here so analysis stages without it stay light."""
    try:
        torch = importlib.import_module("torch")
    except ImportError:
        return
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


class NvmlGpuGuard:
    """Only one model on the GPU at a time."""

    def __init__(self, empty_cache: Callable[[], None] = _empty_torch_cache) -> None:
        self._lock = threading.Lock()
        self._empty_cache = empty_cache

    def status(self) -> GpuStatus | None:
        try:
            pynvml.nvmlInit()
            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                name = pynvml.nvmlDeviceGetName(handle)
                memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
                temperature = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
            finally:
                pynvml.nvmlShutdown()
        except pynvml.NVMLError as error:
            log.warning("gpu.status_unavailable", message=str(error))
            return None
        return GpuStatus(
            name=name.decode() if isinstance(name, bytes) else str(name),
            vram_free_mb=int(memory.free) // BYTES_PER_MB,
            temp_c=int(temperature),
        )

    def loaded(self, load: Callable[[], T]) -> AbstractContextManager[T]:
        return self._loaded(load)

    @contextmanager
    def _loaded(self, load: Callable[[], T]) -> Iterator[T]:
        with self._lock:
            model: T | None = None
            try:
                model = load()
                yield model
            finally:
                del model
                gc.collect()
                self._empty_cache()
