"""The join's concat list. Spec: specs/04-pipeline.md#stages [BUG-009]"""

from __future__ import annotations

from pathlib import Path

from app.adapters.ffmpeg_compositor import concat_listing


def test_bug_009_each_part_states_its_exact_length_so_a_short_last_frame_cannot_drift() -> None:
    listing = concat_listing([Path("work/s0.mp4"), Path("work/s1.mp4")], [24, 10], 30)

    assert listing == (
        "file 'work/s0.mp4'\nduration 0.800000\nfile 'work/s1.mp4'\nduration 0.333333\n"
    )


def test_bug_009_lengths_add_up_to_the_frame_count_over_a_long_edit() -> None:
    frames = [7, 23, 11] * 100
    listing = concat_listing([Path("p.mp4")] * len(frames), frames, 30)

    stated = [
        float(line.split()[1]) for line in listing.splitlines() if line.startswith("duration")
    ]

    assert abs(sum(stated) - sum(frames) / 30) < 1e-3
