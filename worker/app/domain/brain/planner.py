"""Builds the edit plan from analysis results. Spec: specs/05-editing-brain.md

Pure and deterministic: the same inputs and seed always give the same plan.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.analysis import StoredAnalysis
from app.domain.brain.assign import Assignment, Candidate, assign_shots, split_long_slots
from app.domain.brain.effects import plan_effects
from app.domain.brain.music_map import DEFAULT_LENGTH_SEC, choose_edit_window
from app.domain.brain.pacing import beat_grid, build_slots
from app.domain.brain.scoring import score_shots
from app.domain.brain.style_rules import pick_style
from app.domain.brain.validate import validate_plan
from app.domain.errors import ErrorCode, RenderError
from app.domain.models import RenderSettings
from app.domain.music import MusicMap
from app.domain.plan import EditPlan, Effect, MusicWindow, Output, Segment, Source
from app.domain.shots import ShotMeasure

LONG_EDGES = {"4K": 3840, "6K": 6144, "8K": 7680}
PANO_PREFIX = "OSMO360"
VIDEO_SEGMENT = "video"


@dataclass(frozen=True)
class ClipInput:
    asset_id: str
    analysis: StoredAnalysis


def output_size(ratio: str, quality: str) -> tuple[int, int]:
    """Long edge from the quality; short edge from the ratio, rounded to even."""
    long_edge = LONG_EDGES[quality]
    across, down = (int(part) for part in ratio.split(":"))
    if across >= down:
        return long_edge, _even(long_edge * down / across)
    return _even(long_edge * across / down), long_edge


def build_edit_plan(
    music_asset_id: str,
    music: MusicMap,
    clips: Sequence[ClipInput],
    settings: RenderSettings,
) -> EditPlan:
    rng = random.Random(settings.seed)
    style, style_note = pick_style(settings.style, music.bpm)
    window = choose_edit_window(
        music.downbeats,
        music.sections,
        music.energy,
        music.energy_hop_sec,
        music.duration_sec,
        float(settings.length_sec or DEFAULT_LENGTH_SEC),
    )
    candidates = _candidates(clips)
    if not candidates:
        raise RenderError("None of the clips has a usable shot", ErrorCode.PLAN_INVALID)

    longest = max(
        window_part.end - window_part.start
        for candidate in candidates
        for window_part in candidate.shot.measure.usable
    )
    slots = split_long_slots(build_slots(music, window, style), beat_grid(music), longest)
    assignments = assign_shots(slots, candidates, music, rng)
    effects = plan_effects(assignments, music, style)
    analyses = {clip.asset_id: clip.analysis for clip in clips}
    width, height = output_size(settings.ratio, settings.quality)

    notes = [note for note in (style_note, _pano_note(clips)) if note]
    plan = EditPlan(
        seed=settings.seed,
        style=style.id,
        output=Output(
            ratio=settings.ratio,
            quality=settings.quality,
            width=width,
            height=height,
            fps=settings.fps,
            mode=settings.mode,
        ),
        music=MusicWindow(
            asset_id=music_asset_id, start=window.start, end=window.end, bpm=music.bpm
        ),
        grade=style.grade,
        segments=tuple(
            _segment(index, assignment, effect_list, analyses[assignment.candidate.asset_id])
            for index, (assignment, effect_list) in enumerate(
                zip(assignments, effects, strict=True), start=1
            )
        ),
        log=tuple(notes),
    )
    validate_plan(plan, music)
    return plan


def _candidates(clips: Sequence[ClipInput]) -> list[Candidate]:
    owners: list[tuple[str, ShotMeasure]] = [
        (clip.asset_id, shot) for clip in clips for shot in clip.analysis.shots
    ]
    scored = score_shots([shot for _, shot in owners])
    ranked = sorted(shot.measure.motion for shot in scored)
    denominator = max(1, len(ranked) - 1)
    return [
        Candidate(asset_id, shot, ranked.index(shot.measure.motion) / denominator)
        for (asset_id, _), shot in zip(owners, scored, strict=True)
        if shot.is_usable and shot.measure.usable
    ]


def _segment(
    index: int, assignment: Assignment, effects: tuple[Effect, ...], analysis: StoredAnalysis
) -> Segment:
    slot = assignment.slot
    return Segment(
        id=f"s{index}",
        asset_id=assignment.candidate.asset_id,
        type=VIDEO_SEGMENT,
        src_in=assignment.src_in,
        src_out=assignment.src_out,
        at=slot.start,
        duration=round(slot.duration, 4),
        effects=effects,
        source=Source(
            camera_mode=analysis.camera_mode,
            log_profile=analysis.log_profile,
            native_fps=analysis.fps,
        ),
    )


def _pano_note(clips: Sequence[ClipInput]) -> str | None:
    if any((clip.analysis.camera_mode or "").startswith(PANO_PREFIX) for clip in clips):
        return "360 clips are center-cropped until 360 reframing arrives in Phase 3"
    return None


def _even(value: float) -> int:
    return round(value / 2) * 2
