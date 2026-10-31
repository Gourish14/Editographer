"""GPU temperature from NVML. Spec: specs/09-local-setup.md#cool-mode"""

from __future__ import annotations

from app.ports.gpu_guard import GpuGuard


class NvmlThermalGuard:
    """Reads through GpuGuard, the one place that talks to NVML."""

    def __init__(self, gpu: GpuGuard) -> None:
        self._gpu = gpu

    def temperature_c(self) -> int | None:
        status = self._gpu.status()
        return status.temp_c if status else None
