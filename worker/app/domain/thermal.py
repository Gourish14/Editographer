"""Cool mode decisions. Spec: specs/09-local-setup.md#cool-mode"""

from __future__ import annotations

PAUSE_AT_C = 83
RESUME_AT_C = 75
STAGE_PAUSE_SEC = 10
WATCH_EVERY_SEC = 2


def should_stay_paused(paused: bool, temp_c: int | None) -> bool:
    """Pause at 83 °C and hold until 75 °C. With no reading, never hold a render forever."""
    if temp_c is None:
        return False
    return temp_c > RESUME_AT_C if paused else temp_c >= PAUSE_AT_C
