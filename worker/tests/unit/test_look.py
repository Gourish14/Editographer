"""Tests for look, sound and cool mode rules. Spec: specs/05-editing-brain.md#b5 #b8 [T-303]"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.application.cool_mode import CoolCompositor, CoolDown, cool_compositor
from app.application.job_runner import CancellationToken
from app.application.look import audio_mix, segment_look
from app.domain.errors import JobCancelledError
from app.domain.look import (
    IMPACT,
    SFX_GAIN_DB,
    WHOOSH,
    WHOOSH_PEAK_SEC,
    motion_blur_amount,
    planned_sfx,
    transition_frames,
)
from app.domain.plan import (
    EditPlan,
    Effect,
    Grade,
    MusicWindow,
    Output,
    Segment,
    SfxCue,
    Source,
    Transition,
)
from app.domain.thermal import should_stay_paused
from app.ports.render import NO_LOOK, EncodeProfile, SegmentLook

SOURCE = Source(camera_mode=None, log_profile=None, native_fps=30)
LOG_SOURCE = Source(camera_mode=None, log_profile="DLOGM", native_fps=30)
PROFILE = EncodeProfile(320, 180, 30, 28, "p2", False)
FLASH_HIT = Effect(type="flash", at=0.0, duration=0.08)
ZOOM = Effect(type="zoomPunch", at=0.0, duration=0.25, strength=0.1)


def segment(index: int, at: float, **fields: object) -> Segment:
    values: dict[str, object] = {
        "id": f"s{index}",
        "asset_id": f"v{index}",
        "type": "video",
        "src_in": 1.0,
        "src_out": 2.0,
        "at": at,
        "duration": 1.0,
        "source": SOURCE,
    }
    return Segment.model_validate(values | fields)


def plan_of(*segments: Segment, sfx: tuple[SfxCue, ...] = ()) -> EditPlan:
    return EditPlan(
        seed=1,
        style="velocity",
        output=Output(ratio="16:9", quality="4K", width=3840, height=2160, fps=30, mode="fast"),
        music=MusicWindow(asset_id="m", start=10.0, end=13.0, bpm=120),
        grade=Grade(lut="teal_orange", intensity=0.8, grain=0.0),
        segments=segments,
        sfx=sfx,
    )


def test_b5_a_hard_cut_has_no_transition_frames() -> None:
    assert transition_frames(Transition(), 30, 30) == 0
    assert transition_frames(Transition(type="cut", duration=0.2), 30, 30) == 0
    assert transition_frames(Transition(type="spin", duration=0.0), 30, 30) == 0


def test_b5_transition_length_is_whole_frames_and_keeps_one_clean_frame() -> None:
    assert transition_frames(Transition(type="spin", duration=0.18), 60, 30) == 11
    assert transition_frames(Transition(type="spin", duration=2.0), 30, 15) == 14
    assert transition_frames(Transition(type="spin", duration=0.01), 30, 15) == 1
    assert transition_frames(Transition(type="spin", duration=0.2), 30, 1) == 0


@pytest.mark.parametrize("kind", ["whip_left", "whip_right", "zoom_whip", "zoom_through", "spin"])
def test_b5_blur_amount_is_fx_intensity_times_0_7_for_fast_transitions(kind: str) -> None:
    moving = segment(0, 10.0, transition_out=Transition(type=kind, duration=0.2))

    assert motion_blur_amount(moving, 0.9) == pytest.approx(0.63)


def test_b5_a_zoom_gets_motion_blur_and_a_still_segment_does_not() -> None:
    assert motion_blur_amount(segment(0, 10.0, effects=(ZOOM,)), 0.5) == pytest.approx(0.35)
    assert motion_blur_amount(segment(0, 10.0), 0.9) == 0.0
    glitch = segment(0, 10.0, transition_out=Transition(type="glitch", duration=0.2))
    assert motion_blur_amount(glitch, 0.9) == 0.0


def test_b5_a_blur_amount_in_the_plan_wins() -> None:
    named = segment(0, 10.0, effects=(Effect(type="motionBlur", amount=0.2), ZOOM))

    assert motion_blur_amount(named, 0.9) == 0.2


def test_b8_whoosh_peaks_on_the_cut_and_impact_lands_on_the_drop_at_minus_18() -> None:
    plan = plan_of(
        segment(0, 10.0, transition_out=Transition(type="whip_left", duration=0.2)),
        segment(1, 11.0, effects=(FLASH_HIT,)),
        segment(2, 12.0),
    )

    cues = planned_sfx(plan)

    assert [(cue.type, cue.at) for cue in cues] == [
        (WHOOSH, 11.0 - WHOOSH_PEAK_SEC),
        (IMPACT, 11.0),
    ]
    assert {cue.gain_db for cue in cues} == {SFX_GAIN_DB}


def test_b8_a_flash_inside_a_segment_is_not_a_drop_hit() -> None:
    late_flash = Effect(type="flash", at=0.5, duration=0.08)

    assert planned_sfx(plan_of(segment(0, 10.0, effects=(late_flash,)))) == ()


def test_b8_the_last_segment_has_no_cut_to_whoosh_on() -> None:
    plan = plan_of(segment(0, 10.0, transition_out=Transition(type="spin", duration=0.2)))

    assert planned_sfx(plan) == ()


def test_b8_sfx_written_in_the_plan_are_used_as_they_are() -> None:
    cue = SfxCue(type="whoosh", at=10.5, gain_db=-12.0)
    plan = plan_of(
        segment(0, 10.0, transition_out=Transition(type="spin", duration=0.2)),
        segment(1, 11.0),
        sfx=(cue,),
    )

    assert planned_sfx(plan) == (cue,)


def test_look_carries_grade_blur_and_the_next_clip_with_its_own_log_profile() -> None:
    plan = plan_of(
        segment(0, 10.0, effects=(ZOOM,)), segment(1, 11.0, source=LOG_SOURCE, src_in=4.0)
    )
    sources = {"v0": Path("a.mp4"), "v1": Path("b.mp4")}

    look = segment_look(plan, 0, sources)

    assert look.grade == plan.grade
    assert look.motion_blur == pytest.approx(0.63)
    assert look.next_clip is not None
    assert (look.next_clip.source, look.next_clip.src_in) == (Path("b.mp4"), 4.0)
    assert look.next_clip.log_profile == "DLOGM"


def test_the_last_segment_has_no_next_clip() -> None:
    plan = plan_of(segment(0, 10.0))

    assert segment_look(plan, 0, {"v0": Path("a.mp4")}).next_clip is None


def test_b8_mix_times_start_at_the_first_frame_and_only_kept_clips_duck() -> None:
    plan = plan_of(segment(0, 10.0, effects=(FLASH_HIT,)), segment(1, 11.0, keep_audio=True))

    mix = audio_mix(plan, {"v0": Path("a.mp4"), "v1": Path("b.mp4")})

    assert [(cue.type, cue.at) for cue in mix.sfx] == [(IMPACT, 0.0)]
    assert [(clip.source, clip.at) for clip in mix.speech] == [(Path("b.mp4"), 1.0)]


@pytest.mark.parametrize(
    ("paused", "temp_c", "expected"),
    [
        (False, 82, False),
        (False, 83, True),
        (True, 76, True),
        (True, 75, False),
        (False, None, False),
        (True, None, False),
    ],
)
def test_cool_mode_pauses_at_83_and_resumes_at_75(
    paused: bool, temp_c: int | None, expected: bool
) -> None:
    assert should_stay_paused(paused, temp_c) is expected


class FakeThermal:
    def __init__(self, *readings: int | None) -> None:
        self.readings = list(readings)

    def temperature_c(self) -> int | None:
        return self.readings.pop(0)


class Sleeper:
    def __init__(self) -> None:
        self.slept: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.slept.append(seconds)


class FakeCompositor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, SegmentLook]] = []
        self.joined: list[Path] = []

    def render_segment(
        self,
        source: Path,
        segment: Segment,
        frames: int,
        profile: EncodeProfile,
        target: Path,
        look: SegmentLook = NO_LOOK,
    ) -> None:
        self.calls.append((segment.id, look))

    def join(self, parts: object, target: Path) -> None:
        self.joined.append(target)


def test_cool_mode_rests_10_s_in_2_s_steps_between_gpu_stages() -> None:
    sleeper = Sleeper()

    CoolDown(FakeThermal(60), CancellationToken(), sleeper).stage_pause()

    assert sleeper.slept == [2, 2, 2, 2, 2]


def test_cool_mode_holds_above_83_checking_every_2_s_until_75() -> None:
    sleeper = Sleeper()

    CoolDown(FakeThermal(84, 80, 76, 75), CancellationToken(), sleeper).wait_until_cool()

    assert sleeper.slept == [2, 2, 2]


def test_cool_mode_does_not_wait_below_83() -> None:
    sleeper = Sleeper()

    CoolDown(FakeThermal(82), CancellationToken(), sleeper).wait_until_cool()

    assert sleeper.slept == []


def test_a_cancelled_render_stops_waiting_for_the_gpu_to_cool() -> None:
    token = CancellationToken()
    token.cancel()

    with pytest.raises(JobCancelledError):
        CoolDown(FakeThermal(90, 90), token, Sleeper()).wait_until_cool()
    with pytest.raises(JobCancelledError):
        CoolDown(FakeThermal(60), token, Sleeper()).stage_pause()


def test_cool_compositor_rests_once_then_checks_before_each_segment() -> None:
    inner = FakeCompositor()
    sleeper = Sleeper()
    thermal = FakeThermal(60, 90, 70, 60)
    look = SegmentLook(motion_blur=0.5)
    wrapped = CoolCompositor(inner, CoolDown(thermal, CancellationToken(), sleeper))

    for index in range(3):
        wrapped.render_segment(Path("a"), segment(index, 10.0), 30, PROFILE, Path("b"), look)
    wrapped.join([], Path("joined"))

    assert [call[0] for call in inner.calls] == ["s0", "s1", "s2"]
    assert inner.calls[0][1] is look
    assert sleeper.slept == [2, 2, 2, 2, 2, 2]
    assert inner.joined == [Path("joined")]


def test_cool_mode_off_leaves_the_compositor_unchanged() -> None:
    inner = FakeCompositor()
    token = CancellationToken()

    assert cool_compositor(inner, FakeThermal(), False, token) is inner
    assert cool_compositor(inner, None, True, token) is inner
    assert isinstance(cool_compositor(inner, FakeThermal(), True, token), CoolCompositor)
