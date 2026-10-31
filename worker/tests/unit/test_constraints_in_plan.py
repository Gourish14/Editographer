"""Constraints changing the plan, and the styles behind them.

Spec: specs/05-editing-brain.md#b3-pacing-and-style-presets-pacingpy, #b4-shot-assignment-assignpy,
#b5-effect-rules-effectspy, #b10-llm-director-and-fallback-directorpy [T-202]
"""

from __future__ import annotations

import dataclasses
import random

import pytest

from app.domain.brain.assign import Candidate, assign_shots, prompt_fit, select_candidates
from app.domain.brain.effects import FLASH, SHAKE, ZOOM_PUNCH, effects_turned_off
from app.domain.brain.pacing import Slot, build_slots
from app.domain.brain.planner import ClipInput, build_edit_plan
from app.domain.brain.scoring import ScoredShot
from app.domain.brain.style_rules import (
    ANIME,
    CAR,
    CINEMATIC,
    HYPE,
    SPORTS,
    STYLES,
    TRAVEL,
    VELOCITY,
    StylePreset,
    fallback_style,
)
from app.domain.brain.validate import validate_plan
from app.domain.constraints import NO_CONSTRAINTS, Constraints, Direction, DirectorDecision
from app.domain.models import RenderSettings
from app.domain.music import MusicMap, SectionKind
from app.domain.plan import EditPlan
from app.domain.shots import ShotMeasure, TimeWindow
from tests.unit.test_planner import analysis, music_map

SETTINGS = RenderSettings("9:16", "4K", 30, "auto", "fast", 12, None, False, 42)
CAR_CLIPS = ("c0", "c1", "c2")


def tagged(*tags: str, motion: float = 1.0, seconds: float = 10.0) -> ShotMeasure:
    return ShotMeasure(
        start=0.0,
        end=seconds,
        motion=motion,
        subject=0.6,
        sharpness=100.0,
        stability=0.8,
        luma=0.5,
        peak_time=1.0,
        usable=(TimeWindow(start=0.0, end=seconds),),
        tags=tags,
    )


def mixed_clips() -> list[ClipInput]:
    """Three car clips and three beach clips, the beach ones scoring higher."""
    cars = [ClipInput(f"c{i}", analysis(tagged("car", motion=float(i + 1)))) for i in range(3)]
    beaches = [
        ClipInput(f"b{i}", analysis(tagged("beach", motion=float(i + 10)))) for i in range(3)
    ]
    return cars + beaches


def planned(
    constraints: Constraints = NO_CONSTRAINTS,
    settings: RenderSettings = SETTINGS,
    clips: list[ClipInput] | None = None,
    music: MusicMap | None = None,
) -> EditPlan:
    direction = Direction(DirectorDecision(constraints=constraints))
    return build_edit_plan("m1", music or music_map(), clips or mixed_clips(), settings, direction)


def used_assets(plan: EditPlan) -> set[str]:
    return {segment.asset_id for segment in plan.segments}


def effect_types(plan: EditPlan) -> set[str]:
    return {effect.type for segment in plan.segments for effect in segment.effects}


# B3


@pytest.mark.parametrize(
    ("style", "intro", "build", "drop", "break_", "outro", "fx"),
    [
        (VELOCITY, 2, 1, (0.5, 1), 2, 4, 0.9),
        (HYPE, 1, 0.5, (0.5,), 1, 2, 1.0),
        (CINEMATIC, 4, 2, (2,), 4, 8, 0.3),
        (ANIME, 2, 1, (0.5,), 2, 4, 0.9),
        (TRAVEL, 4, 2, (1,), 4, 4, 0.5),
        (CAR, 2, 1, (0.5,), 2, 4, 0.8),
        (SPORTS, 2, 1, (0.5,), 2, 4, 0.8),
    ],
)
def test_b3_table(
    style: StylePreset,
    intro: float,
    build: float,
    drop: tuple[float, ...],
    break_: float,
    outro: float,
    fx: float,
) -> None:
    assert style.cut_beats[SectionKind.INTRO] == (intro,)
    assert style.cut_beats[SectionKind.BUILD] == (build,)
    assert style.cut_beats[SectionKind.VERSE] == (build,)
    assert style.cut_beats[SectionKind.DROP] == drop
    assert style.cut_beats[SectionKind.BREAK] == (break_,)
    assert style.cut_beats[SectionKind.OUTRO] == (outro,)
    assert style.fx_intensity == fx


def test_b3_there_are_seven_styles_with_their_own_grades() -> None:
    assert len(STYLES) == 7
    assert len({preset.grade.lut for preset in STYLES.values()}) == 7


@pytest.mark.parametrize("style", sorted(STYLES))
def test_b3_every_style_makes_a_valid_plan(style: str) -> None:
    music = music_map()

    plan = build_edit_plan(
        "m1", music, mixed_clips(), dataclasses.replace(SETTINGS, style=style, length_sec=30)
    )

    assert plan.style == style
    assert plan.log == ()
    validate_plan(plan, music)


def test_b3_hype_cuts_faster_than_velocity_on_the_build() -> None:
    music = music_map()
    window = music.edit_window

    def builds(style: StylePreset) -> int:
        slots = build_slots(music, window, style)
        return sum(1 for slot in slots if slot.section is not SectionKind.DROP)

    assert builds(HYPE) >= builds(VELOCITY)


# B4 prompt fit


def test_b4_prompt_fit_is_1_5_for_each_included_tag() -> None:
    assert prompt_fit(("car",), (), ()) == 1.0
    assert prompt_fit(("car",), ("car",), ()) == 1.5
    assert prompt_fit(("car", "night"), ("car", "night"), ()) == 2.25


def test_b4_prompt_fit_is_0_if_an_excluded_tag_matches() -> None:
    assert prompt_fit(("car", "night"), ("car",), ("night",)) == 0.0


def test_b4_only_car_shots_uses_only_the_car_clips() -> None:
    plan = planned(Constraints(include_tags=("car",)))

    assert used_assets(plan) <= set(CAR_CLIPS)
    assert not any("skipped" in line for line in plan.log)


def test_b4_without_a_prompt_the_stronger_beach_shots_appear() -> None:
    assert used_assets(planned()) - set(CAR_CLIPS)


def test_b4_excluded_shots_never_appear() -> None:
    plan = planned(Constraints(exclude_tags=("beach",)))

    assert used_assets(plan) <= set(CAR_CLIPS)


def test_b4_too_few_matches_are_topped_up_with_the_best_others() -> None:
    clips = [
        ClipInput("c0", analysis(tagged("car", seconds=2.0))),
        ClipInput("b0", analysis(tagged("beach", motion=9.0))),
        ClipInput("b1", analysis(tagged("beach", motion=2.0))),
        ClipInput("b2", analysis(tagged("beach", motion=3.0))),
    ]

    plan = planned(Constraints(include_tags=("car",)), clips=clips)

    assert "c0" in used_assets(plan)
    assert "b0" in used_assets(plan)
    assert "b1" not in used_assets(plan)
    assert any("Too little 'car' footage" in line for line in plan.log)


def test_b4_enough_matched_footage_needs_no_top_up() -> None:
    plan = planned(Constraints(include_tags=("car",)), dataclasses.replace(SETTINGS, length_sec=8))

    assert not any("Too little" in line for line in plan.log)


def test_b4_a_tag_nothing_has_is_logged_and_the_edit_still_happens() -> None:
    plan = planned(Constraints(include_tags=("drone",)))

    assert "Prompt request 'drone' skipped: no matching footage" in plan.log
    assert plan.segments


def test_b4_shots_without_tags_cannot_match_and_say_so() -> None:
    clips = [ClipInput(f"v{i}", analysis(tagged(motion=float(i + 1)))) for i in range(4)]

    plan = planned(Constraints(include_tags=("car",)), clips=clips)

    assert "Prompt request 'car' skipped: no matching footage" in plan.log


def test_b4_excluding_every_shot_is_ignored_and_logged() -> None:
    clips = [ClipInput(f"v{i}", analysis(tagged("car", motion=float(i + 1)))) for i in range(3)]

    plan = planned(Constraints(exclude_tags=("car",)), clips=clips)

    assert plan.segments
    assert any("Every shot is excluded" in line for line in plan.log)


def test_b4_exclude_beats_include_on_the_same_shot() -> None:
    clips = [
        ClipInput("c0", analysis(tagged("car", "night"))),
        ClipInput("c1", analysis(tagged("car", motion=2.0))),
        ClipInput("c2", analysis(tagged("car", motion=3.0))),
    ]

    plan = planned(Constraints(include_tags=("car",), exclude_tags=("night",)), clips=clips)

    assert "c0" not in used_assets(plan)


def candidate(
    asset: str, start: float, score: float = 0.8, tags: tuple[str, ...] = ()
) -> Candidate:
    measure = tagged(*tags).model_copy(update={"start": start, "end": start + 10.0})
    window = TimeWindow(start=start, end=start + 10.0)
    shot = ScoredShot(measure.model_copy(update={"usable": (window,)}), score, None)
    return Candidate(asset, shot, 0.5)


def test_b4_prompt_fit_lifts_a_weaker_matching_shot_over_a_stronger_one() -> None:
    weak_match = candidate("car", 0.0, 0.5, ("car",))
    strong_other = candidate("sea", 0.0, 0.6)
    slots = [Slot(0.0, 1.0, SectionKind.BUILD, 1.0, False)]
    music = music_map()
    only = Constraints(include_tags=("car",))

    without = assign_shots(slots, [weak_match, strong_other], music, random.Random(1))
    within = assign_shots(slots, [weak_match, strong_other], music, random.Random(1), only)

    assert without[0].candidate.asset_id == "sea"
    assert within[0].candidate.asset_id == "car"


def test_b4_select_candidates_keeps_capture_order() -> None:
    pool = [candidate("a", 0.0), candidate("b", 0.0, tags=("car",)), candidate("c", 0.0)]

    kept, _ = select_candidates(pool, Constraints(include_tags=("car",)), 25.0)

    assert [c.asset_id for c in kept] == ["a", "b", "c"]


# B4 order


def order_of(plan: EditPlan) -> list[str]:
    seen: list[str] = []
    for segment in plan.segments:
        if segment.asset_id not in seen:
            seen.append(segment.asset_id)
    return seen


def even_clips() -> list[ClipInput]:
    return [ClipInput(f"v{i}", analysis(tagged(motion=2.0))) for i in range(5)]


def test_b4_chronological_order_follows_the_clips() -> None:
    plan = planned(Constraints(order="chronological"), clips=even_clips())

    assert order_of(plan) == ["v0", "v1", "v2", "v3", "v4"]


def test_b4_chronological_order_cycles_through_every_shot_when_it_reuses_them() -> None:
    plan = planned(Constraints(order="chronological"), clips=even_clips())
    assets = [segment.asset_id for segment in plan.segments]

    assert assets[:7] == ["v0", "v1", "v2", "v3", "v4", "v0", "v1"]


def test_b4_chronological_order_keeps_the_no_repeat_rule() -> None:
    clips = [
        ClipInput("v0", analysis(*[tagged(motion=2.0).model_copy(update={"start": s, "end": s + 3,
                  "usable": (TimeWindow(start=s, end=s + 3),)}) for s in (0.0, 3.0, 6.0)])),
        ClipInput("v1", analysis(tagged(motion=2.0))),
    ]  # fmt: skip

    assets = [s.asset_id for s in planned(Constraints(order="chronological"), clips=clips).segments]

    assert all(a != b for a, b in zip(assets, assets[1:], strict=False))


def test_b4_travel_is_chronological_by_itself() -> None:
    settings = dataclasses.replace(SETTINGS, style="travel")

    assert order_of(planned(settings=settings, clips=even_clips()))[:3] == ["v0", "v1", "v2"]


def test_b4_other_styles_are_energy_driven() -> None:
    assert order_of(planned(clips=even_clips())) != ["v0", "v1", "v2", "v3", "v4"]


# Constraints on effects, length and style


REACHES_THE_DROP = dataclasses.replace(SETTINGS, style="velocity", length_sec=30)


def test_b5_no_shakes_removes_them_and_keeps_the_rest() -> None:
    before = effect_types(planned(settings=REACHES_THE_DROP))
    after = effect_types(planned(Constraints(effects_off=("shake",)), REACHES_THE_DROP))

    assert SHAKE in before
    assert SHAKE not in after
    assert {FLASH, ZOOM_PUNCH} <= after


def test_b5_accents_turn_to_zooms_when_shakes_are_off() -> None:
    def zooms(plan: EditPlan) -> int:
        return sum(1 for s in plan.segments for e in s.effects if e.type == ZOOM_PUNCH)

    assert zooms(planned(Constraints(effects_off=("shake",)), REACHES_THE_DROP)) > zooms(
        planned(settings=REACHES_THE_DROP)
    )


def test_b5_every_effect_can_be_turned_off() -> None:
    off = Constraints(effects_off=("shake", "flash", "zoompunch"))

    assert effect_types(planned(settings=REACHES_THE_DROP)) != set()
    assert effect_types(planned(off, REACHES_THE_DROP)) - {"motionBlur"} == set()


@pytest.mark.parametrize("name", ["shakes", "camera shake", "SHAKE"])
def test_b5_effect_names_are_forgiving(name: str) -> None:
    assert effects_turned_off((name,)) == {SHAKE}


def test_b5_an_unknown_effect_off_is_logged() -> None:
    plan = planned(Constraints(effects_off=("sparkles",)))

    assert "Prompt request 'no sparkles' skipped: no such effect in this edit" in plan.log


def test_b5_fx_intensity_replaces_the_styles() -> None:
    def strongest(plan: EditPlan) -> float:
        return max(e.strength or 0.0 for s in plan.segments for e in s.effects)

    stronger = Constraints(fx_intensity=1.0)
    weaker = Constraints(fx_intensity=0.2)
    assert strongest(planned(settings=REACHES_THE_DROP)) == pytest.approx(0.9)
    assert strongest(planned(weaker, REACHES_THE_DROP)) == pytest.approx(0.2)
    assert strongest(planned(stronger, REACHES_THE_DROP)) == pytest.approx(1.0)


def test_b5_fx_intensity_0_means_no_effects() -> None:
    assert effect_types(planned(Constraints(fx_intensity=0.0), REACHES_THE_DROP)) == set()


def test_the_prompt_duration_beats_the_length_setting() -> None:
    plan = planned(Constraints(duration_sec=8.0), dataclasses.replace(SETTINGS, length_sec=30))

    assert plan.music.end - plan.music.start <= 8.0


def test_the_prompts_style_beats_the_style_setting() -> None:
    plan = planned(Constraints(style="cinematic"), dataclasses.replace(SETTINGS, style="velocity"))

    assert plan.style == "cinematic"
    assert plan.grade.lut == "film"


def test_the_style_setting_beats_the_directors_own_pick() -> None:
    direction = Direction(DirectorDecision(style="hype"))
    settings = dataclasses.replace(SETTINGS, style="travel")

    assert build_edit_plan("m1", music_map(), mixed_clips(), settings, direction).style == "travel"


def test_the_directors_pick_is_used_on_auto() -> None:
    direction = Direction(DirectorDecision(style="sports"))

    assert build_edit_plan("m1", music_map(), mixed_clips(), SETTINGS, direction).style == "sports"


def test_without_a_direction_the_prompt_goes_through_the_keyword_rules() -> None:
    settings = dataclasses.replace(SETTINGS, prompt="cinematic, no shakes")

    plan = build_edit_plan("m1", music_map(), mixed_clips(), settings)

    assert plan.style == "cinematic"
    assert SHAKE not in effect_types(plan)


# The plan log


def test_b9_unmapped_requests_reach_the_plan_log() -> None:
    plan = planned(Constraints(unmapped=("add drone shots",)))

    assert "Prompt request 'add drone shots' skipped: nothing maps to it" in plan.log


def test_b9_slowmo_is_recorded_in_the_plan_log() -> None:
    plan = planned(Constraints(slowmo_at=(SectionKind.DROP,)), REACHES_THE_DROP)

    assert any(line.startswith("Slow motion on: drop;") for line in plan.log)


def test_b9_text_and_effects_on_are_recorded_in_the_plan_log() -> None:
    plan = planned(Constraints(text=("GOA 2026",), effects_on=("tinyplanet",)))

    assert "Text 'GOA 2026' requested; text overlays arrive in Phase 3" in plan.log
    assert "Effect 'tinyplanet' requested; not available yet" in plan.log


def test_b9_a_huge_request_is_cut_short_in_the_log() -> None:
    plan = planned(Constraints(unmapped=("x" * 1000,)))

    assert len(plan.log[0]) < 200


def test_direction_notes_come_first_in_the_log() -> None:
    direction = Direction(notes=("AI director unavailable",))

    plan = build_edit_plan("m1", music_map(), mixed_clips(), SETTINGS, direction)

    assert plan.log[0] == "AI director unavailable"


def test_constraints_keep_the_plan_deterministic() -> None:
    only = Constraints(include_tags=("car",), effects_off=("shake",))

    assert planned(only) == planned(only)


# B10 fallback, in order


def with_bpm(bpm: float, drop_energy: float | None = 0.9) -> MusicMap:
    """A map with the given tempo; `None` removes every drop."""
    music = music_map()
    sections = tuple(
        section.model_copy(
            update={
                "kind": SectionKind.VERSE if drop_energy is None else section.kind,
                "mean_energy": drop_energy or 0.5,
            }
        )
        for section in music.sections
    )
    return music.model_copy(update={"bpm": bpm, "sections": sections})


CARS = [("car",), ("vehicle",), ("car",), ("beach",)]
BEACHES = [("beach",), ("mountain",), ("outdoor", "sky"), ("car",)]
PLAIN: list[tuple[str, ...]] = [("indoor",), ("people",)]


@pytest.mark.parametrize(
    ("music", "tags", "expected"),
    [
        (with_bpm(140.0), CARS, HYPE),
        (with_bpm(180.0, None), BEACHES, HYPE),
        (with_bpm(120.0), CARS, VELOCITY),
        (with_bpm(139.9, 0.75), BEACHES, VELOCITY),
        (with_bpm(120.0, 0.74), CARS, CAR),
        (with_bpm(90.0, None), CARS, CAR),
        (with_bpm(125.0, None), BEACHES, TRAVEL),
        (with_bpm(90.0, None), BEACHES, TRAVEL),
        (with_bpm(99.9, None), PLAIN, CINEMATIC),
        (with_bpm(100.0, None), PLAIN, VELOCITY),
        (with_bpm(130.0, None), PLAIN, VELOCITY),
        (with_bpm(110.0, None), [], VELOCITY),
    ],
)
def test_b10_fallback_rules_in_order(
    music: MusicMap, tags: list[tuple[str, ...]], expected: StylePreset
) -> None:
    assert fallback_style(music, tags) is expected


def test_b10_half_the_shots_is_not_most_of_them() -> None:
    assert fallback_style(with_bpm(110.0, None), [("car",), ("indoor",)]) is VELOCITY


def test_b10_auto_uses_the_rules_with_real_tags() -> None:
    clips = [ClipInput(f"c{i}", analysis(tagged("car", motion=float(i + 1)))) for i in range(4)]

    plan = build_edit_plan("m1", with_bpm(110.0, None), clips, SETTINGS)

    assert plan.style == "car"
