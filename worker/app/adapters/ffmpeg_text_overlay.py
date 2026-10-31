"""FFmpeg overlay filters for text layer PNGs. Spec: specs/06-edit-plan-schema.md (text)

The caller adds each PNG as an input with `input_args` and appends `overlay_chain` to its
filter graph. An item with a subject matte also gets the subject drawn back over its text
(text behind subject, spec 05 B8), on the same 10-bit pipeline.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from app.domain.brain.text_rules import TextItem

FADE_SEC = 0.1


def input_args(png: Path, item: TextItem, fps: int) -> list[str]:
    """Looped still input that lasts as long as the item."""
    return ["-loop", "1", "-framerate", str(fps), "-t", f"{item.duration:.3f}", "-i", str(png)]


def matte_input_args(folder: Path, fps: int) -> list[str]:
    """A gray PNG sequence at the edit's frame rate, starting at its first frame."""
    return ["-framerate", str(fps), "-i", str(folder / "%06d.png")]


def overlay_chain(
    base_label: str,
    items: Sequence[TextItem],
    first_input: int,
    out_label: str = "vtext",
    mattes: Mapping[int, int] | None = None,
    fps: int = 30,
) -> str:
    """Filter graph that overlays item i (input first_input + i) on base_label at its time.

    Each layer fades in and out over 0.1 s and is shifted to `at` on the timeline. `mattes` maps
    an item index to the input holding its subject matte; that item's subject is then overlaid on
    top of its text, so the text sits behind the subject.
    """
    mattes = mattes or {}
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
        window = f"enable='between(t,{item.at:.3f},{item.at + item.duration:.3f})'"
        if index not in mattes:
            parts.append(f"[{current}][{layer}]overlay=eof_action=pass:format=auto:{window}[{nxt}]")
            current = nxt
            continue
        parts += _behind_subject(current, layer, item, mattes[index], fps, window, nxt, index)
        current = nxt
    return ";".join(parts)


def _behind_subject(
    base: str, layer: str, item: TextItem, matte: int, fps: int, window: str, out: str, index: int
) -> list[str]:
    """Text over the picture, then the picture's subject (cut out by its matte) over the text."""
    first = round(item.at * fps)
    count = round(item.duration * fps)
    keep, titled, cut = f"keep{index}", f"ti{index}", f"cut{index}"
    return [
        f"[{base}]split=2[sa{index}][{keep}]",
        f"[sa{index}][{layer}]overlay=eof_action=pass:format=auto:{window}[{titled}]",
        f"[{keep}]trim=start_frame={first}:end_frame={first + count},setpts=PTS-STARTPTS,"
        f"format=yuva420p10le[{keep}s]",
        f"[{matte}:v]format=gray,trim=end_frame={count},setpts=PTS-STARTPTS[mk{index}]",
        f"[{keep}s][mk{index}]alphamerge,setpts=PTS+{item.at:.3f}/TB[{cut}]",
        f"[{titled}][{cut}]overlay=eof_action=pass:format=auto:{window}[{out}]",
    ]
