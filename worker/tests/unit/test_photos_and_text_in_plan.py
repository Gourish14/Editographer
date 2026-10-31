"""Photos under B4, text[] and kept speech in the plan. Spec: specs/05-editing-brain.md [T-404]"""

from __future__ import annotations

from app.domain.analysis import StoredAnalysis, StoredSpeech
from app.domain.brain.planner import ClipInput, build_edit_plan
from app.domain.constraints import Constraints, Direction, DirectorDecision
from app.domain.photo import DepthSummary, FocusBox, FocusSource, PhotoAnalysis, PhotoMotion
from app.domain.plan import EditPlan
from tests.unit.test_planner import SETTINGS, analysis, clips, measure, music_map


def photo(motion: PhotoMotion = PhotoMotion.KEN_BURNS) -> StoredAnalysis:
    depth = DepthSummary(0.9, 120, "depth.png") if motion is PhotoMotion.PARALLAX else None
    found = PhotoAnalysis(4000, 3000, FocusBox(0.4, 0.3, 0.2, 0.2, FocusSource.FACE), motion, depth)
    return analysis().model_copy(update={"photo": found})


def photos(count: int) -> list[ClipInput]:
    return [ClipInput(f"p{i}", photo()) for i in range(count)]


def mixed(count: int = 20) -> EditPlan:
    return build_edit_plan("m1", music_map(), clips(), SETTINGS, None, photos(count))


def test_b4_photos_fill_at_most_30_percent_of_the_slots() -> None:
    kinds = [segment.type for segment in mixed().segments]

    assert 0 < kinds.count("photo") <= len(kinds) * 0.3


def test_b4_a_photo_is_never_on_a_drop() -> None:
    plan = mixed()
    drops = [s for s in music_map().sections if s.kind.value == "DROP"]

    for segment in plan.segments:
        if segment.type == "photo":
            assert not any(d.start <= segment.at < d.end for d in drops)


def test_b4_photos_only_fills_every_slot_on_the_grid() -> None:
    plan = build_edit_plan("m1", music_map(), [], SETTINGS, None, photos(3))

    assert {segment.type for segment in plan.segments} == {"photo"}
    assert {segment.asset_id for segment in plan.segments} == {"p0", "p1", "p2"}
    assert all(segment.motion is not None for segment in plan.segments)


def test_b7_a_deep_photo_gets_parallax() -> None:
    deep = [ClipInput("p0", photo(PhotoMotion.PARALLAX))]

    plan = build_edit_plan("m1", music_map(), [], SETTINGS, None, deep)

    motion = plan.segments[0].motion
    assert motion is not None
    assert (motion.type, motion.depth) == ("parallax", True)


def test_b8_prompt_text_is_scheduled_into_the_plan() -> None:
    direction = Direction(DirectorDecision(constraints=Constraints(text=("GOA 2026",))))

    plan = build_edit_plan("m1", music_map(), clips(), SETTINGS, direction)

    assert [item.content for item in plan.text] == ["GOA 2026"]
    assert plan.music.start <= plan.text[0].at < plan.music.end
    assert not any("arrive" in note and "Text" in note for note in plan.log)


def spoken_clip() -> list[ClipInput]:
    words = (("hello", 1.0, 1.4), ("world", 1.5, 1.9))
    speech = StoredSpeech(spans=((1.0, 1.9),), words=words)
    base = analysis(measure(0.0, 10.0, 1.0))
    return [ClipInput("v0", base.model_copy(update={"speech": speech}))]


def test_b8_a_segment_with_speech_keeps_its_audio_and_gets_captions() -> None:
    plan = build_edit_plan("m1", music_map(), spoken_clip(), SETTINGS)

    kept = [s for s in plan.segments if s.keep_audio]
    assert kept
    assert all(s.src_in < 1.9 and s.src_out > 1.0 for s in kept)
    captions = [item for item in plan.text if item.anim == "caption"]
    assert captions
    assert all(plan.music.start <= item.at < plan.music.end for item in captions)


def test_b8_no_speech_means_no_kept_audio() -> None:
    assert not any(segment.keep_audio for segment in mixed().segments)
