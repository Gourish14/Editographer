"""Turns a plan into what the compositor and mixer need. Spec: specs/04-pipeline.md#stages (6, 8)"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from app.domain.brain.style_rules import STYLES
from app.domain.look import motion_blur_amount, planned_sfx
from app.domain.plan import EditPlan
from app.ports.render import AudioMix, KeptClipAudio, NextClip, SegmentLook, SfxPlacement

DEFAULT_FX_INTENSITY = 0.5
PHOTO_SEGMENT = "photo"


def segment_look(plan: EditPlan, index: int, sources: Mapping[str, Path]) -> SegmentLook:
    """The look of one segment: the plan's grade, its motion blur and the clip after it."""
    segment = plan.segments[index]
    preset = STYLES.get(plan.style)
    fx_intensity = preset.fx_intensity if preset else DEFAULT_FX_INTENSITY
    following = plan.segments[index + 1] if index + 1 < len(plan.segments) else None
    next_clip = None
    if following is not None and PHOTO_SEGMENT not in (segment.type, following.type):
        next_clip = NextClip(
            sources[following.asset_id], following.src_in, following.source.log_profile, following
        )
    return SegmentLook(plan.grade, motion_blur_amount(segment, fx_intensity), next_clip)


def audio_mix(plan: EditPlan, sources: Mapping[str, Path]) -> AudioMix:
    """Plan times are on the music timeline; the mix starts at the edit's first frame."""
    start = plan.music.start
    sfx = tuple(
        SfxPlacement(cue.type, round(cue.at - start, 4), cue.gain_db) for cue in planned_sfx(plan)
    )
    speech = tuple(
        KeptClipAudio(
            sources[segment.asset_id],
            segment.src_in,
            round(segment.at - start, 4),
            segment.duration,
        )
        for segment in plan.segments
        if segment.keep_audio
    )
    return AudioMix(sfx, speech)
