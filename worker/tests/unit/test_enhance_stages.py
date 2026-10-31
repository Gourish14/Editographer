"""GPU stage rules that need no GPU. Spec: specs/04-pipeline.md#stages (6, 7),
specs/09-local-setup.md#cool-mode [T-405]"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from app.adapters.ffmpeg_filters import NO_FRAMING, Framing, path_crop, segment_filter
from app.application.enhance_stages import (
    UpscaleStage,
    needs_rife,
    working_size,
)
from app.application.render_job import _stage_ends
from app.domain.brain.ramps import ramp_speed
from app.domain.errors import JobCancelledError
from app.domain.models import AssetInput, AssetType
from app.domain.plan import EditPlan, Grade, MusicWindow, Output, ReframePoint, Segment, Source
from app.ports.enhance import FrameSize
from app.ports.frames import UpscaleSpec


def plan_of(segments: tuple[Segment, ...], ratio: str = "9:16") -> EditPlan:
    width, height = (2160, 3840) if ratio == "9:16" else (3840, 2160)
    return EditPlan(
        seed=1,
        style="velocity",
        output=Output(ratio=ratio, quality="4K", width=width, height=height, fps=30, mode="max"),
        music=MusicWindow(asset_id="m", start=0.0, end=2.0, bpm=120.0),
        grade=Grade(lut="film", intensity=1.0, grain=0.0),
        segments=segments,
    )


def video(kind: str = "video", **fields: object) -> Segment:
    return Segment(
        id="s1",
        asset_id="v1",
        type=kind,
        at=0.0,
        duration=1.0,
        source=Source(camera_mode=None, log_profile=None, native_fps=30.0),
        **fields,  # type: ignore[arg-type]
    )


def asset(width: int, height: int) -> AssetInput:
    return AssetInput("v1", AssetType.VIDEO, "a.mp4", None, None, None, 8.0, width, height, 30.0)


def test_spec04_max_composes_at_the_size_a_flat_source_holds() -> None:
    size = working_size(plan_of((video(),)), {"v1": asset(1920, 1080)})

    assert (size.width, size.height, size.upscale) == (606, 1076, True)


def test_spec08_rule_8_a_360_view_holds_source_width_times_fov_over_360() -> None:
    size = working_size(plan_of((video("video360"),)), {"v1": asset(6000, 3000)})

    assert size.width == 1500  # 6000 x 90 / 360 for a 9:16 view
    assert size.upscale


def test_spec04_a_source_that_already_holds_the_output_is_not_upscaled() -> None:
    size = working_size(plan_of((video(),), "16:9"), {"v1": asset(3840, 2160)})

    assert (size.width, size.height, size.upscale) == (3840, 2160, False)


def test_spec04_sources_of_unknown_size_leave_the_output_size_alone() -> None:
    assert not working_size(plan_of((video(),)), {}).upscale


def test_spec04_max_weights_compose_30_upscale_35() -> None:
    assert _stage_ends(20, 90, None) == (90, 90)
    assert _stage_ends(20, 90, FrameSize(2160, 3840)) == (43, 70)


def test_b6_only_a_rife_curve_needs_the_rife_stage() -> None:
    assert needs_rife(video(speed=ramp_speed(30.0)))
    assert not needs_rife(video(speed=ramp_speed(120.0)))
    assert not needs_rife(video())


def test_b7_a_crop_path_moves_in_straight_lines_and_stays_inside_the_frame() -> None:
    path = (ReframePoint(t=0.0, x=0.3, y=0.5), ReframePoint(t=1.0, x=0.7, y=0.5))

    expression = path_crop(path, 9 / 16)

    assert "clip((" in expression
    assert "iw-ow" in expression
    assert expression.count("(") == expression.count(")")


def test_b7_a_long_crop_path_is_thinned() -> None:
    path = tuple(ReframePoint(t=i * 0.25, x=0.5, y=0.5) for i in range(200))

    assert path_crop(path, 1.0).count("lt(t,") <= 2 * 24 + 2


def test_b6_the_retime_is_the_first_filter_and_the_camera_the_last_before_effects() -> None:
    chain = segment_filter(
        (), 540, 960, 30, False, None, Framing(retime="PTS", camera="v360=e:flat")
    )

    steps = chain.split(",")
    assert steps[0] == "setpts='PTS'"
    assert steps.index("v360=e:flat") > steps.index("fps=30")
    assert "crop=" not in chain
    assert segment_filter((), 540, 960, 30, False, None, NO_FRAMING).startswith("fps=30,")


class Upscaler:
    def __init__(self, frames: int) -> None:
        self.frames = frames

    def upscale_video(self, spec: UpscaleSpec, on_frame: Callable[[int], None]) -> None:
        for done in range(1, self.frames + 1):
            on_frame(done)


class Cancelled:
    def raise_if_cancelled(self) -> None:
        raise JobCancelledError()


class Token:
    def raise_if_cancelled(self) -> None:
        return None


def spec(frames: int) -> UpscaleSpec:
    return UpscaleSpec(
        Path("a.mp4"),
        Path("b.mp4"),
        FrameSize(10, 10),
        FrameSize(40, 40),
        frames,
        30,
        19,
        "p5",
        True,
    )


def test_spec09_upscaling_reports_every_frame_and_stops_on_cancel() -> None:
    seen: list[int] = []

    UpscaleStage(Upscaler(3)).run(spec(3), Token(), lambda done, total: seen.append(done))  # type: ignore[arg-type]

    assert seen == [1, 2, 3]
    with pytest.raises(JobCancelledError):
        UpscaleStage(Upscaler(3)).run(spec(3), Cancelled(), lambda done, total: None)  # type: ignore[arg-type]


class Rests:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def stage_pause(self) -> None:
        self.calls.append("pause")

    def wait_until_cool(self) -> None:
        self.calls.append("cool")


def test_spec09_cool_mode_rests_before_upscaling_and_checks_between_batches() -> None:
    rests = Rests()

    UpscaleStage(Upscaler(25), rests).run(spec(25), Token(), lambda done, total: None)  # type: ignore[arg-type]

    assert rests.calls == ["pause", "cool", "cool"]
