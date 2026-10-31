"""Tests for pacing, assignment, effects and validation. Spec: specs/05-editing-brain.md [T-112]"""

from __future__ import annotations

import dataclasses
import random

import pytest

from app.domain.analysis import StoredAnalysis
from app.domain.brain.assign import Assignment, Candidate, assign_shots, split_long_slots
from app.domain.brain.effects import SHAKE, plan_effects
from app.domain.brain.music_map import MusicFeatures, build_music_map
from app.domain.brain.pacing import MIN_SEGMENT_SEC, Slot, beat_grid, build_slots
from app.domain.brain.planner import ClipInput, build_edit_plan, output_size
from app.domain.brain.scoring import ScoredShot
from app.domain.brain.style_rules import CINEMATIC, VELOCITY, pick_style
from app.domain.brain.validate import validate_plan
from app.domain.errors import ErrorCode, RenderError
from app.domain.models import RenderSettings
from app.domain.music import EditWindow, MusicMap, SectionKind
from app.domain.plan import EditPlan
from app.domain.shots import ShotMeasure, TimeWindow

HOP = 0.05
BEAT = 0.5
BAR = 4 * BEAT


def music_map(parts: list[tuple[int, float]] | None = None, beat: float = BEAT) -> MusicMap:
    parts = parts or [(8, 0.2), (16, 1.0), (8, 0.25), (16, 1.0), (8, 0.3)]
    rms: list[float] = []
    for bars, level in parts:
        rms.extend([level] * round(bars * 4 * beat / HOP))
    duration = len(rms) * HOP
    beats = tuple(round(i * beat, 4) for i in range(int(duration / beat)))
    onset = [0.0] * len(rms)
    for index, time in enumerate(beats):
        frame = round(time / HOP)
        if frame < len(onset):
            onset[frame] = 1.0 if index % 4 == 0 else 0.5
    return build_music_map(
        MusicFeatures(duration, beats, beats[::4], tuple(rms), tuple(onset), HOP)
    )


def measure(start: float = 0.0, end: float = 10.0, motion: float = 1.0) -> ShotMeasure:
    return ShotMeasure(
        start=start,
        end=end,
        motion=motion,
        subject=0.6,
        sharpness=100.0,
        stability=0.8,
        luma=0.5,
        peak_time=start + 1.0,
        usable=(TimeWindow(start=start, end=end),),
    )


def analysis(*shots: ShotMeasure) -> StoredAnalysis:
    return StoredAnalysis(
        file_hash="h",
        codec="h264",
        width=1920,
        height=1080,
        fps=30.0,
        rotation=0,
        duration_sec=30.0,
        transfer=None,
        bit_depth=8,
        camera_mode="FLAT",
        log_profile=None,
        native_slow_mo=False,
        shots=shots,
    )


def clips(count: int = 6) -> list[ClipInput]:
    return [
        ClipInput(
            f"v{i}",
            analysis(measure(0.0, 10.0, float(i + 1)), measure(10.0, 20.0, float(i) + 0.5)),
        )
        for i in range(count)
    ]


SETTINGS = RenderSettings("9:16", "4K", 30, "velocity", "fast", 30, None, False, 42)


def plan(settings: RenderSettings = SETTINGS, music: MusicMap | None = None) -> EditPlan:
    return build_edit_plan("m1", music or music_map(), clips(), settings)


# B3


def window_of(music: MusicMap) -> EditWindow:
    return music.edit_window


def test_b3_slots_cover_the_window_exactly() -> None:
    music = music_map()
    slots = build_slots(music, window_of(music), VELOCITY)

    assert slots[0].start == music.edit_window.start
    assert slots[-1].end == music.edit_window.end
    for earlier, later in zip(slots, slots[1:], strict=False):
        assert earlier.end == later.start


def test_b3_every_slot_starts_on_the_beat_grid() -> None:
    music = music_map()
    grid = set(beat_grid(music))

    assert all(slot.start in grid for slot in build_slots(music, window_of(music), VELOCITY))


def test_b3_the_grid_has_beats_and_their_midpoints() -> None:
    assert beat_grid(music_map())[:3] == (0.0, 0.25, 0.5)


def test_b3_velocity_alternates_half_and_full_beats_on_the_drop() -> None:
    music = music_map()
    drop = [
        slot
        for slot in build_slots(music, window_of(music), VELOCITY)
        if slot.section is SectionKind.DROP
    ]

    assert {round(slot.duration, 3) for slot in drop} == {BEAT / 2, BEAT}


def test_b3_cinematic_cuts_slower_than_velocity() -> None:
    music = music_map()

    assert len(build_slots(music, window_of(music), CINEMATIC)) < len(
        build_slots(music, window_of(music), VELOCITY)
    )


def test_b3_no_slot_is_shorter_than_a_quarter_second() -> None:
    music = music_map(beat=0.4)

    slots = build_slots(music, window_of(music), VELOCITY)

    assert min(slot.duration for slot in slots) >= MIN_SEGMENT_SEC


def test_b3_a_new_section_always_starts_a_slot() -> None:
    music = music_map()
    starts = {slot.start for slot in build_slots(music, window_of(music), CINEMATIC)}

    for section in music.sections:
        if music.edit_window.start < section.start < music.edit_window.end:
            assert section.start in starts


# B4


def slot(start: float = 0.0, end: float = 1.0, section: SectionKind = SectionKind.DROP) -> Slot:
    return Slot(start, end, section, 1.0, False)


def candidate(asset: str, start: float = 0.0, end: float = 10.0, rank: float = 0.5) -> Candidate:
    shot = dataclasses.replace(ScoredShot(measure(start, end), 0.8, None))
    return Candidate(asset, shot, rank)


def assign(slots: list[Slot], pool: list[Candidate], seed: int = 1) -> tuple[Assignment, ...]:
    return assign_shots(slots, pool, music_map(), random.Random(seed))


def test_b4_two_consecutive_slots_never_share_source_clip() -> None:
    slots = [slot(float(i), float(i + 1)) for i in range(20)]
    pool = [candidate(f"v{i}", rank=i / 3) for i in range(4)]

    result = assign(slots, pool)

    for earlier, later in zip(result, result[1:], strict=False):
        assert earlier.candidate.asset_id != later.candidate.asset_id


def test_b4_a_single_clip_may_repeat_because_nothing_else_exists() -> None:
    slots = [slot(float(i), float(i + 1)) for i in range(3)]

    assert len(assign(slots, [candidate("v0")])) == 3


def test_b4_a_shot_is_reused_only_after_every_shot_is_used() -> None:
    slots = [slot(float(i), float(i + 1)) for i in range(4)]
    pool = [candidate(f"v{i}", rank=i / 3) for i in range(4)]

    assert len({a.candidate.asset_id for a in assign(slots, pool)}) == 4


def test_b4_a_reused_shot_gets_a_different_window() -> None:
    slots = [slot(float(i), float(i + 1)) for i in range(5)]

    result = assign(slots, [candidate("v0", 0.0, 10.0)])

    spans = sorted((a.src_in, a.src_out) for a in result)
    for earlier, later in zip(spans, spans[1:], strict=False):
        assert earlier[1] <= later[0]


def test_b4_drop_slots_prefer_shots_with_motion_in_the_top_half() -> None:
    slots = [slot(float(i), float(i + 1)) for i in range(10)]
    pool = [candidate(f"v{i}", rank=i / 29) for i in range(30)]

    result = assign(slots, pool)
    energetic = sum(1 for a in result if a.candidate.motion_rank >= 0.5)

    assert energetic >= 7


def test_b4_the_peak_moment_lands_on_the_slots_beat() -> None:
    result = assign([slot()], [candidate("v0")])

    assert result[0].src_in == 1.0


def test_b4_the_window_moves_only_enough_to_fit_the_usable_part() -> None:
    result = assign([slot(0.0, 1.0)], [candidate("v0", 0.0, 1.5)])

    assert result[0].src_in == 0.5
    assert result[0].src_out == 1.5


def test_b4_a_slot_longer_than_every_shot_is_split_on_the_grid() -> None:
    grid = (0.0, 1.0, 2.0, 3.0, 4.0)

    parts = split_long_slots([slot(0.0, 4.0)], grid, longest=1.5)

    assert [(part.start, part.end) for part in parts] == [
        (0.0, 1.0),
        (1.0, 2.0),
        (2.0, 3.0),
        (3.0, 4.0),
    ]


def test_b4_no_candidates_fails_clearly() -> None:
    with pytest.raises(RenderError) as failure:
        assign([slot()], [])

    assert failure.value.code is ErrorCode.PLAN_INVALID


def test_b4_same_seed_same_assignment() -> None:
    slots = [slot(float(i), float(i + 1)) for i in range(12)]
    pool = [candidate(f"v{i}", rank=0.5) for i in range(6)]

    assert assign(slots, pool, 7) == assign(slots, pool, 7)


def test_b4_a_new_seed_changes_ties() -> None:
    slots = [slot(float(i), float(i + 1)) for i in range(12)]
    pool = [candidate(f"v{i}", rank=0.5) for i in range(6)]

    assert assign(slots, pool, 7) != assign(slots, pool, 8)


# B5


def test_b5_the_first_beat_of_a_drop_gets_flash_zoom_and_shake() -> None:
    first_drop = next(
        segment for segment in plan().segments if any(e.type == "flash" for e in segment.effects)
    )

    assert {effect.type for effect in first_drop.effects} >= {"flash", "zoomPunch", "shake"}


def test_b5_shakes_stay_under_40_percent_of_beats() -> None:
    result = plan()
    music = music_map()
    beats = sum(1 for b in music.beats if result.music.start <= b.time < result.music.end)
    shakes = sum(1 for s in result.segments for e in s.effects if e.type == SHAKE)

    assert 0 < shakes <= beats * 0.4


def test_b5_strength_scales_with_the_styles_fx_intensity() -> None:
    def strongest(style: str) -> float:
        settings = dataclasses.replace(SETTINGS, style=style)
        return max(
            effect.strength or 0.0
            for segment in plan(settings).segments
            for effect in segment.effects
        )

    assert strongest("cinematic") < strongest("velocity")


def test_b5_effects_never_run_past_their_segment() -> None:
    for segment in plan().segments:
        for effect in segment.effects:
            assert effect.at + effect.duration <= segment.duration + 1e-6


def test_b5_plan_effects_gives_one_entry_per_assignment() -> None:
    music = music_map()
    assignments = assign([slot(0.0, 1.0), slot(1.0, 2.0)], [candidate("a"), candidate("b")])

    assert len(plan_effects(assignments, music, VELOCITY)) == 2


# B11 and the whole plan


def test_b11_a_plan_from_the_planner_passes_validation() -> None:
    validate_plan(plan(), music_map())


def test_b11_a_segment_off_the_beat_is_refused() -> None:
    good = plan()
    moved = good.segments[1].model_copy(update={"at": good.segments[1].at + 0.1})
    bad = good.model_copy(update={"segments": (good.segments[0], moved, *good.segments[2:])})

    with pytest.raises(RenderError) as failure:
        validate_plan(bad, music_map())

    assert failure.value.code is ErrorCode.PLAN_INVALID
    assert "off the beat" in str(failure.value)


def test_b11_a_gap_is_refused() -> None:
    good = plan()
    bad = good.model_copy(update={"segments": good.segments[:-1]})

    with pytest.raises(RenderError, match="ends at"):
        validate_plan(bad, music_map())


def test_b11_a_source_window_shorter_than_its_slot_is_refused() -> None:
    good = plan()
    short = good.segments[0].model_copy(update={"src_out": good.segments[0].src_in})
    bad = good.model_copy(update={"segments": (short, *good.segments[1:])})

    with pytest.raises(RenderError, match="source window"):
        validate_plan(bad, music_map())


def test_the_plan_matches_the_requested_output() -> None:
    result = plan()

    assert (result.output.width, result.output.height) == (2160, 3840)
    assert result.music.asset_id == "m1"
    assert result.seed == 42
    assert result.style == "velocity"


def test_the_plan_json_uses_the_schema_names() -> None:
    document = plan().model_dump(by_alias=True)
    segment = document["segments"][0]

    assert {"assetId", "srcIn", "srcOut", "at", "duration", "transitionOut", "source"} <= set(
        segment
    )
    assert document["music"]["assetId"] == "m1"


def test_same_inputs_and_seed_give_the_same_plan() -> None:
    assert plan() == plan()


def test_make_another_version_changes_the_plan() -> None:
    assert plan() != plan(dataclasses.replace(SETTINGS, seed=43))


def test_the_user_length_limits_the_edit() -> None:
    result = plan(dataclasses.replace(SETTINGS, length_sec=10))

    assert result.music.end - result.music.start <= 10.0


def test_a_project_of_only_rejected_shots_fails_clearly() -> None:
    dark = [ClipInput("v0", analysis(measure().model_copy(update={"luma": 0.0})))]

    with pytest.raises(RenderError) as failure:
        build_edit_plan("m1", music_map(), dark, SETTINGS)

    assert failure.value.code is ErrorCode.PLAN_INVALID


@pytest.mark.parametrize(
    ("ratio", "quality", "expected"),
    [
        ("16:9", "4K", (3840, 2160)),
        ("9:16", "4K", (2160, 3840)),
        ("1:1", "4K", (3840, 3840)),
        ("4:5", "4K", (3072, 3840)),
        ("4:3", "4K", (3840, 2880)),
        ("21:9", "4K", (3840, 1646)),
        ("16:9", "6K", (6144, 3456)),
        ("9:16", "6K", (3456, 6144)),
        ("1:1", "6K", (6144, 6144)),
        ("4:5", "6K", (4916, 6144)),
        ("4:3", "6K", (6144, 4608)),
        ("21:9", "6K", (6144, 2634)),
        ("16:9", "8K", (7680, 4320)),
        ("9:16", "8K", (4320, 7680)),
        ("1:1", "8K", (7680, 7680)),
        ("4:5", "8K", (6144, 7680)),
        ("4:3", "8K", (7680, 5760)),
        ("21:9", "8K", (7680, 3292)),
    ],
)
def test_every_size_in_the_overview_table(
    ratio: str, quality: str, expected: tuple[int, int]
) -> None:
    assert output_size(ratio, quality) == expected


def test_b3_every_style_can_be_requested_without_a_note() -> None:
    music = music_map()

    for style in ("velocity", "hype", "cinematic", "anime", "travel", "car", "sports"):
        preset, note = pick_style(style, music, [])
        assert preset.id == style
        assert note is None


def test_a_style_that_does_not_exist_is_noted() -> None:
    preset, note = pick_style("disco", music_map(), [])

    assert preset is VELOCITY
    assert note == "Style 'disco' does not exist; used velocity"
