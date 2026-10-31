"""Cool mode around GPU work. Spec: specs/09-local-setup.md#cool-mode

FFmpeg cannot be paused from outside on Windows, so the watch acts at the next safe point: before
each segment. Entry point: cool_compositor(). A GPU stage that is not a compositor, like upscaling,
calls CoolDown.stage_pause() before it starts and wait_until_cool() between its batches.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from pathlib import Path

import structlog

from app.application.job_runner import CancellationToken
from app.domain.plan import Segment
from app.domain.thermal import STAGE_PAUSE_SEC, WATCH_EVERY_SEC, should_stay_paused
from app.ports.render import NO_LOOK, Compositor, EncodeProfile, SegmentLook
from app.ports.thermal import ThermalGuard

log = structlog.get_logger()


class CoolDown:
    """Waits that can always be cancelled."""

    def __init__(
        self,
        thermal: ThermalGuard,
        token: CancellationToken,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._thermal = thermal
        self._token = token
        self._sleep = sleep

    def stage_pause(self) -> None:
        """The 10 s rest before a GPU stage, then the temperature check."""
        for _ in range(STAGE_PAUSE_SEC // WATCH_EVERY_SEC):
            self._token.raise_if_cancelled()
            self._sleep(WATCH_EVERY_SEC)
        self.wait_until_cool()

    def wait_until_cool(self) -> None:
        """Returns at once below 83 °C; otherwise holds, checking every 2 s, down to 75 °C."""
        temp_c = self._thermal.temperature_c()
        if not should_stay_paused(False, temp_c):
            return
        log.info("cool_mode.paused", tempC=temp_c)
        while should_stay_paused(True, temp_c):
            self._token.raise_if_cancelled()
            self._sleep(WATCH_EVERY_SEC)
            temp_c = self._thermal.temperature_c()
        log.info("cool_mode.resumed", tempC=temp_c)


class CoolCompositor:
    """A Compositor that rests before its first segment and checks before every other one."""

    def __init__(self, inner: Compositor, cool_down: CoolDown) -> None:
        self._inner = inner
        self._cool_down = cool_down
        self._started = False

    def render_segment(
        self,
        source: Path,
        segment: Segment,
        frames: int,
        profile: EncodeProfile,
        target: Path,
        look: SegmentLook = NO_LOOK,
    ) -> None:
        if self._started:
            self._cool_down.wait_until_cool()
        else:
            self._started = True
            self._cool_down.stage_pause()
        self._inner.render_segment(source, segment, frames, profile, target, look)

    def join(self, parts: Sequence[Path], target: Path) -> None:
        self._inner.join(parts, target)


def cool_compositor(
    compositor: Compositor,
    thermal: ThermalGuard | None,
    enabled: bool,
    token: CancellationToken,
) -> Compositor:
    """The compositor for one GPU stage: wrapped when cool mode is on, unchanged when it is off."""
    if not enabled or thermal is None:
        return compositor
    return CoolCompositor(compositor, CoolDown(thermal, token))
