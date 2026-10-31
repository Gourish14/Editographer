"""Port for following a picked subject through a 360 clip.

Spec: specs/08-osmo360.md (rule 5, subject follow), specs/05-editing-brain.md#b7
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.domain.models import FollowPoint
from app.domain.shots import SubjectSample


@dataclass(frozen=True)
class FollowTrack:
    """Where the picked subject was, in source time and as shares of the equirect frame.

    `lost` holds the source times where tracking ended before the window did (the subject left
    or SAM 2 lost it). Empty `samples` means the subject was never found.
    """

    samples: tuple[SubjectSample, ...] = ()
    lost: tuple[float, ...] = ()


class SubjectFollower(Protocol):
    def follow(
        self, video: Path, point: FollowPoint, start: float, end: float, folder: Path
    ) -> FollowTrack:
        """Follows the subject tapped at `point` over source seconds `start` to `end`.

        Tracks forward and backward from the tap time. Never raises for a lost subject: the
        track just stops, and `lost` says where. Raises only for a real failure.
        """
        ...
