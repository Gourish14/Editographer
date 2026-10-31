"""Port for the GPU temperature. Spec: specs/09-local-setup.md#cool-mode"""

from __future__ import annotations

from typing import Protocol


class ThermalGuard(Protocol):
    def temperature_c(self) -> int | None:
        """Current GPU temperature, or None when it cannot be read."""
        ...
