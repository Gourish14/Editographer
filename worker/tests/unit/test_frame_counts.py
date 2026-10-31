"""Cuts stay on their frames. Spec: specs/10-roadmap.md#phase-1--core-engine [T-118]"""

from __future__ import annotations

from app.application.render_job import cut_frames, frame_counts
from app.domain.plan import EditPlan, Grade, MusicWindow, Output, Segment, Source

FPS = 30


def plan(cuts: list[float], end: float, start: float = 16.3) -> EditPlan:
    """Durations are rounded to 4 places, as the planner stores them."""
    edges = [*cuts, end]
    return EditPlan(
        seed=1,
        style="velocity",
        output=Output(ratio="16:9", quality="4K", width=3840, height=2160, fps=FPS, mode="fast"),
        music=MusicWindow(asset_id="m", start=start, end=end, bpm=118.0),
        grade=Grade(lut="none", intensity=0.0, grain=0.0),
        segments=tuple(
            Segment(
                id=f"s{index}",
                asset_id="a",
                type="video",
                src_in=0.0,
                src_out=later - earlier,
                at=earlier,
                duration=round(later - earlier, 4),
                source=Source(camera_mode=None, log_profile=None, native_fps=None),
            )
            for index, (earlier, later) in enumerate(zip(edges, edges[1:], strict=False))
        ),
    )


def test_gate_counts_add_up_to_the_window_exactly() -> None:
    beats = [16.3 + index * 0.25425 for index in range(233)]

    counts = frame_counts(plan(beats, 75.53))

    assert sum(counts) == round((75.53 - 16.3) * FPS)


def test_gate_a_slot_ending_on_a_half_frame_does_not_gain_a_frame() -> None:
    """Rounded alone, 0.0167 s ends at 0.501 frames, but the next cut starts at 0.499."""
    cuts = [10.0, 10.01663, 10.5]

    assert frame_counts(plan(cuts, 11.0, start=10.0)) == [0, 15, 15]


def test_gate_each_cut_lands_where_its_own_position_says() -> None:
    edit = plan([16.3, 16.8084, 17.3168], 17.8252)

    assert cut_frames(edit) == [0, 15, 31, 46]
