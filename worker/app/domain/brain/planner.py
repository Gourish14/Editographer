"""Builds the edit plan from analysis results. Spec: specs/05-editing-brain.md

Pure and deterministic: the same inputs and seed always give the same plan.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.analysis import StoredAnalysis
from app.domain.brain.assign import (
    Assignment,
    Candidate,
    assign_shots,
    select_candidates,
    split_long_slots,
)
from app.domain.brain.effects import (
    EFFECT_NAMES,
    first_beats_of_drops,
    plan_effects,
    plan_transitions,
    with_motion_blur,
)
from app.domain.brain.framing import follows, frame_segment, is_panoramic
from app.domain.brain.music_map import DEFAULT_LENGTH_SEC, choose_edit_window
from app.domain.brain.pacing import beat_grid, build_slots
from app.domain.brain.photo_plan import photo_segment, photo_slots
from app.domain.brain.prompt_rules import parse_prompt
from app.domain.brain.ramps import ramp_slot_starts, ramp_speed
from app.domain.brain.reframe import FrameSize
from app.domain.brain.scoring import score_shots
from app.domain.brain.style_rules import AUTO, pick_style
from app.domain.brain.text_plan import has_speech, plan_text
from app.domain.brain.validate import validate_plan
from app.domain.constraints import Constraints, Direction, DirectorDecision
from app.domain.errors import ErrorCode, RenderError
from app.domain.models import RenderSettings
from app.domain.music import MusicMap
from app.domain.plan import (
    EditPlan,
    Effect,
    MusicWindow,
    Output,
    Segment,
    Source,
    Speed,
    Transition,
)
from app.domain.shots import ShotMeasure, SubjectSample

LONG_EDGES = {"4K": 3840, "6K": 6144, "8K": 7680}
RAMPED_DROP_STYLE = "velocity"
MAX_NOTE_CHARS = 120


@dataclass(frozen=True)
class ClipInput:
    asset_id: str
    analysis: StoredAnalysis
    follow_track: tuple[SubjectSample, ...] = ()
    """The picked subject's measured track in this clip (source time), empty when none."""


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
    direction: Direction | None = None,
    photos: Sequence[ClipInput] = (),
) -> EditPlan:
    """Without a direction the prompt goes through the keyword rules, so an edit always exists."""
    rng = random.Random(settings.seed)
    chosen = direction or rule_direction(settings.prompt)
    constraints = chosen.decision.constraints
    usable = usable_candidates(clips)
    if not usable and not photos:
        raise RenderError("None of the clips has a usable shot", ErrorCode.PLAN_INVALID)
    photos_only = not usable

    style, style_note = pick_style(
        _requested_style(settings, chosen.decision),
        music,
        [candidate.shot.measure.tags for candidate in usable],
    )
    window = choose_edit_window(
        music.downbeats,
        music.sections,
        music.intensity or music.energy,
        music.energy_hop_sec,
        music.duration_sec,
        constraints.duration_sec or float(settings.length_sec or DEFAULT_LENGTH_SEC),
    )
    transitions: tuple[Transition, ...] = ()
    if photos_only:
        slots = list(build_slots(music, window, style))
        assignments: tuple[Assignment, ...] = ()
        effects: Sequence[tuple[Effect, ...]] = ()
        tag_notes: tuple[str, ...] = ()
    else:
        candidates, tag_notes = select_candidates(usable, constraints, window.end - window.start)
        longest = max(
            window_part.end - window_part.start
            for candidate in candidates
            for window_part in candidate.shot.measure.usable
        )
        slots = split_long_slots(build_slots(music, window, style), beat_grid(music), longest)
        ramped = ramp_slot_starts(
            slots,
            constraints.slowmo_at,
            style.id == RAMPED_DROP_STYLE,
            beat_grid(music),
            1.0 / settings.fps,
        )
        assignments = assign_shots(
            slots,
            candidates,
            music,
            rng,
            constraints,
            constraints.order or style.order,
            ramped,
            settings.follow_point.asset_id if settings.follow_point else None,
        )
        effects = plan_effects(assignments, music, style, constraints)
        panoramic = frozenset(
            clip.asset_id for clip in clips if is_panoramic(clip.analysis.camera_mode)
        )
        transitions = plan_transitions(assignments, style, constraints, panoramic)
    intensity = style.fx_intensity if constraints.fx_intensity is None else constraints.fx_intensity
    framing = _Framing(
        settings,
        intensity,
        [beat.time for beat in music.beats],
        first_beats_of_drops(assignments),
        {clip.asset_id: clip.follow_track for clip in clips},
    )
    analyses = {clip.asset_id: clip.analysis for clip in (*clips, *photos)}
    by_slot = photo_slots(slots, len(photos), photos_only)
    width, height = output_size(settings.ratio, settings.quality)

    notes = (
        *chosen.notes,
        *(note for note in (style_note,) if note),
        *_constraint_notes(constraints, sum(a.ramped for a in assignments)),
        *tag_notes,
    )
    segments = tuple(
        photo_segment(f"s{i + 1}", photos[by_slot[i]].asset_id, slot, photos[by_slot[i]].analysis)
        if i in by_slot
        else _segment(
            i + 1,
            assignments[i],
            effects[i],
            analyses[assignments[i].candidate.asset_id],
            Transition() if i + 1 in by_slot else transitions[i],
            framing,
            i + 1 < len(assignments)
            and assignments[i + 1].slot.section is not assignments[i].slot.section,
        )
        for i, slot in enumerate(slots)
    )
    text, text_notes = plan_text(
        constraints.text, music.downbeats, window, style.id, segments, analyses
    )
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
        segments=segments,
        text=text,
        log=(*notes, *text_notes),
    )
    validate_plan(plan, music)
    return plan


def rule_direction(prompt: str | None, notes: tuple[str, ...] = ()) -> Direction:
    """The keyword parser's reading of the prompt. The style is left to the rules."""
    return Direction(DirectorDecision(constraints=parse_prompt(prompt)), notes)


def usable_candidates(clips: Sequence[ClipInput]) -> list[Candidate]:
    """Every shot worth using, in clip then time order."""
    owners: list[tuple[str, float | None, ShotMeasure]] = [
        (clip.asset_id, clip.analysis.fps, shot) for clip in clips for shot in clip.analysis.shots
    ]
    scored = score_shots([shot for _, _, shot in owners])
    ranked = sorted(shot.measure.motion for shot in scored)
    denominator = max(1, len(ranked) - 1)
    return [
        Candidate(asset_id, shot, ranked.index(shot.measure.motion) / denominator, fps)
        for (asset_id, fps, _), shot in zip(owners, scored, strict=True)
        if shot.is_usable and shot.measure.usable
    ]


def _requested_style(settings: RenderSettings, decision: DirectorDecision) -> str:
    """The prompt's words first, then the user's setting, then the director's own pick."""
    if decision.constraints.style:
        return decision.constraints.style
    if settings.style != AUTO:
        return settings.style
    return decision.style or AUTO


def _constraint_notes(constraints: Constraints, ramps: int) -> list[str]:
    """Everything asked for that this version cannot apply, so nothing is dropped silently."""
    notes: list[str] = []
    if constraints.slowmo_at:
        sections = ", ".join(constraints.slowmo_at)
        if ramps:
            notes.append(f"Slow motion on: {sections}; {ramps} slot(s) got a speed ramp")
        else:
            notes.append(f"Slow motion requested on: {sections}; no slot there fits a ramp")
    notes.extend(
        f"Effect '{_short(name)}' requested; not available yet"
        for name in constraints.effects_on
        if name not in EFFECT_NAMES
    )
    notes.extend(
        f"Prompt request 'no {_short(name)}' skipped: no such effect in this edit"
        for name in constraints.effects_off
        if name not in EFFECT_NAMES
    )
    notes.extend(
        f"Prompt request '{_short(request)}' skipped: nothing maps to it"
        for request in constraints.unmapped
    )
    return notes


def _short(text: str) -> str:
    return text[:MAX_NOTE_CHARS]


@dataclass(frozen=True)
class _Framing:
    """What the planner shares with every segment's framing and look."""

    settings: RenderSettings
    fx_intensity: float
    beats: list[float]
    drop_starts: set[float]
    follow_tracks: dict[str, tuple[SubjectSample, ...]]


def _segment(
    index: int,
    assignment: Assignment,
    effects: tuple[Effect, ...],
    analysis: StoredAnalysis,
    transition: Transition,
    framing: _Framing,
    ends_section: bool,
) -> Segment:
    slot = assignment.slot
    speed = ramp_speed(analysis.fps) if assignment.ramped else Speed()
    size = (
        FrameSize(analysis.width, analysis.height) if analysis.width and analysis.height else None
    )
    framed = frame_segment(
        assignment,
        speed,
        effects,
        analysis.camera_mode,
        size,
        framing.settings.ratio,
        framing.beats,
        slot.start in framing.drop_starts,
        ends_section,
        follows(framing.settings.follow_point, assignment.candidate.asset_id),
        framing.follow_tracks.get(assignment.candidate.asset_id, ()),
    )
    return Segment(
        id=f"s{index}",
        asset_id=assignment.candidate.asset_id,
        type=framed.type,
        src_in=assignment.src_in,
        src_out=assignment.src_out,
        at=slot.start,
        duration=round(slot.duration, 4),
        speed=speed,
        reframe=framed.reframe,
        effects=with_motion_blur(framed.effects, transition, framing.fx_intensity),
        transition_out=transition,
        keep_audio=has_speech(analysis, assignment.src_in, assignment.src_out),
        source=Source(
            camera_mode=analysis.camera_mode,
            log_profile=analysis.log_profile,
            native_fps=analysis.fps,
            width=analysis.width,
        ),
        camera360=framed.camera360,
    )


def _even(value: float) -> int:
    return round(value / 2) * 2
