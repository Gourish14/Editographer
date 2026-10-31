"""FFmpeg overlay filters for text layer PNGs. Spec: specs/06-edit-plan-schema.md (text)

The caller adds each PNG as an input with `input_args` and appends `overlay_chain` to its
filter graph. SAM 2 text-behind-subject is out of scope.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from app.domain.brain.text_rules import TextItem

FADE_SEC = 0.1


def input_args(png: Path, item: TextItem, fps: int) -> list[str]:
    """Looped still input that lasts as long as the item."""
    return ["-loop", "1", "-framerate", str(fps), "-t", f"{item.duration:.3f}", "-i", str(png)]


def overlay_chain(
    base_label: str, items: Sequence[TextItem], first_input: int, out_label: str = "vtext"
) -> str:
    """Filter graph that overlays item i (input first_input + i) on base_label at its time.

    Each layer fades in and out over 0.1 s and is shifted to `at` on the timeline.
    """
    if not items:
        return f"[{base_label}]null[{out_label}]"
    parts: list[str] = []
    current = base_label
    for index, item in enumerate(items):
        fade = min(FADE_SEC, item.duration / 2)
        layer = f"tl{index}"
        nxt = out_label if index == len(items) - 1 else f"vt{index}"
        parts.append(
            f"[{first_input + index}:v]format=rgba,"
            f"fade=t=in:st=0:d={fade:.3f}:alpha=1,"
            f"fade=t=out:st={item.duration - fade:.3f}:d={fade:.3f}:alpha=1,"
            f"setpts=PTS+{item.at:.3f}/TB[{layer}]"
        )
        parts.append(
            f"[{current}][{layer}]overlay=eof_action=pass:format=auto:"
            f"enable='between(t,{item.at:.3f},{item.at + item.duration:.3f})'[{nxt}]"
        )
        current = nxt
    return ";".join(parts)
