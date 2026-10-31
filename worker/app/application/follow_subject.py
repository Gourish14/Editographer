"""Measures the picked subject's track for the 360 camera.

Spec: specs/08-osmo360.md (rule 5 and the subject picker), specs/05-editing-brain.md#b7

The planner is pure, so the track is measured here between two planning passes: the first pass
says which source windows the 360 segments use, the follower measures the subject over them
(SAM 2 through the GPU guard), and the second pass frames the camera on the measurement. Every
way the track can fall short is logged and goes into the plan log, never silent.
"""

from __future__ import annotations

from pathlib import Path

import structlog

from app.domain.brain.framing import VIDEO_360
from app.domain.models import FollowPoint
from app.domain.plan import EditPlan
from app.domain.shots import SubjectSample
from app.ports.subject_follow import FollowTrack, SubjectFollower

log = structlog.get_logger()

MAX_TRACK_SEC = 90.0  # about 360 frames at the tracker's rate: more is not worth the time


class FollowSubject:
    def __init__(self, follower: SubjectFollower) -> None:
        self._follower = follower

    def measure(
        self, plan: EditPlan, asset_id: str, video: Path, point: FollowPoint, folder: Path
    ) -> tuple[tuple[SubjectSample, ...], tuple[str, ...]]:
        """The track of the picked subject in one clip, and the plan notes about it.

        An empty track means the detection track stays in charge (the fallback), with a note.
        """
        segments = [s for s in plan.segments if s.type == VIDEO_360 and s.asset_id == asset_id]
        if not segments:
            return (), ()
        low = min(s.src_in for s in segments)
        high = max(s.src_out for s in segments)
        window = _window(low, high, point.time_sec)
        notes: list[str] = []
        if window[1] - window[0] < max(high, point.time_sec) - min(low, point.time_sec):
            notes.append(
                f"Subject follow: only {window[0]:.1f}s to {window[1]:.1f}s of the clip is "
                "tracked; the camera holds the nearest measured bearing outside it"
            )
        try:
            track = self._follower.follow(video, point, window[0], window[1], folder)
        except Exception as error:  # noqa: BLE001 - tracking is optional, the edit still renders
            log.warning("follow.failed", asset=asset_id, message=str(error))
            return (), (_FAILED_NOTE,)
        if not track.samples:
            log.warning("follow.not_found", asset=asset_id, x=point.x, y=point.y)
            return (), (_NOT_FOUND_NOTE,)
        notes.extend(_lost_notes(track))
        log.info("follow.measured", asset=asset_id, samples=len(track.samples), lost=track.lost)
        return track.samples, tuple(notes)


_FAILED_NOTE = "Subject follow: tracking failed; the camera uses the detected subject instead"
_NOT_FOUND_NOTE = (
    "Subject follow: no subject found at the picked point; "
    "the camera starts there and follows the detected subject"
)


def _lost_notes(track: FollowTrack) -> list[str]:
    return [
        f"Subject follow: subject lost at {time:.1f}s; the camera holds its last bearing there"
        for time in track.lost
    ]


def _window(low: float, high: float, tap: float) -> tuple[float, float]:
    """The source window to track: the segments' span and the tap, at most MAX_TRACK_SEC."""
    start, end = min(low, tap), max(high, tap)
    if end - start <= MAX_TRACK_SEC:
        return start, end
    first = min(max(start, tap - MAX_TRACK_SEC / 2), end - MAX_TRACK_SEC)
    return first, first + MAX_TRACK_SEC
