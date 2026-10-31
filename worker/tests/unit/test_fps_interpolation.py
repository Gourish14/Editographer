"""FEAT-021: RIFE raises the frame rate of slow sources in Max mode.
Spec: specs/04-pipeline.md#stages (6) [T-409]"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from app.application.enhance_stages import RetimeStage, raises_fps
from app.domain.errors import JobCancelledError
from app.domain.plan import Segment, Source


def segment(native: float | None, kind: str = "video") -> Segment:
    return Segment(
        id="s1",
        asset_id="v1",
        type=kind,
        at=0.0,
        duration=1.0,
        source=Source(camera_mode=None, log_profile=None, native_fps=native),
    )


class Token:
    def __init__(self) -> None:
        self.stop = False

    def raise_if_cancelled(self) -> None:
        if self.stop:
            raise JobCancelledError()


class Session:
    def __init__(self, token: Token | None = None, cancel_after: int = 0) -> None:
        self.fractions: list[float] = []
        self.cancel_after = cancel_after
        self.token = token

    def between_files(self, first: Path, second: Path, target: Path, time: float = 0.5) -> None:
        self.fractions.append(round(time, 3))
        target.write_bytes(b"x")
        if self.token and len(self.fractions) >= self.cancel_after:
            self.token.stop = True


class Interpolator:
    def __init__(self, session: Session) -> None:
        self.session_obj = session
        self.sessions = 0

    @contextmanager
    def session(self) -> Iterator[Session]:
        self.sessions += 1
        yield self.session_obj


class Media:
    def __init__(self, count: int) -> None:
        self.count = count

    def extract_frames(
        self, source: Path, start: float, duration: float, fps: float, folder: Path
    ) -> int:
        folder.mkdir(parents=True, exist_ok=True)
        for index in range(self.count):
            (folder / f"{index + 1:06d}.png").write_bytes(b"f")
        return self.count


def test_feat_021_only_a_flat_clip_far_below_the_output_rate_is_interpolated() -> None:
    assert raises_fps(segment(30.0), 60)
    assert raises_fps(segment(24.0), 60)
    assert not raises_fps(segment(60.0), 60)
    assert not raises_fps(segment(50.0), 60)  # fps filter repeats too few frames to matter
    assert not raises_fps(segment(120.0), 60)
    assert not raises_fps(segment(None), 60)
    assert not raises_fps(segment(30.0, "video360"), 60)


def test_feat_021_30_to_60_makes_every_other_frame_with_one_session_and_exact_count(
    tmp_path: Path,
) -> None:
    session = Session()
    interpolator = Interpolator(session)

    patterns = RetimeStage(interpolator, Media(40)).run(  # type: ignore[arg-type]
        [(segment(30.0), tmp_path / "a.mp4", 60)], 60, tmp_path, Token()
    )

    assert interpolator.sessions == 1
    assert len(list((tmp_path / "retime" / "s1" / "out").glob("*.png"))) == 60
    assert session.fractions == [0.5] * 30
    assert patterns["s1"].name == "%06d.png"


def test_feat_021_cancellation_is_checked_between_frames(tmp_path: Path) -> None:
    token = Token()
    session = Session(token, cancel_after=3)

    with pytest.raises(JobCancelledError):
        RetimeStage(Interpolator(session), Media(40)).run(  # type: ignore[arg-type]
            [(segment(30.0), tmp_path / "a.mp4", 60)], 60, tmp_path, token
        )

    assert len(session.fractions) == 3
