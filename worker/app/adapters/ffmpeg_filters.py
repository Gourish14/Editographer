"""Builds FFmpeg filter graphs for a segment. Spec: specs/04-pipeline.md#stages (6)

Pure text building, so it can be tested without FFmpeg. crop cannot change size per frame, so a
zoom scales up per frame and then crops back to the output size.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app.domain.brain.effects import FLASH, SHAKE, ZOOM_PUNCH
from app.domain.plan import Effect, ReframePoint

SHAKE_OVERSCAN = 0.04
SHAKE_MAX_SHARE = 0.015
SHAKE_SPEED_X = 71
SHAKE_SPEED_Y = 53
FLASH_COLOR = "white@0.85"
SHARPEN = "unsharp=5:5:0.6"
WORK_FORMAT = "yuv420p10le"
RGB_FORMAT = "gbrp10le"
HOLD_LAST_FRAME = "tpad=stop=-1:stop_mode=clone"
ZERO_TIME = "setpts=PTS-STARTPTS"
GRAIN_SCALE = 20
MOTION_BLUR_MIN_FRAMES = 2
MOTION_BLUR_EXTRA_FRAMES = 3

# Spec 06 transition types FFmpeg's xfade can do. A new type only needs a new row. planet_morph
# is a stand-in here: the true morph is a 360 shader.
XFADE_BY_TRANSITION = {
    "flash": "fadewhite",
    "luma_fade": "fadegrays",
    "zoom_through": "zoomin",
    "zoom_whip": "zoomin",
    "whip_left": "slideleft",
    "whip_right": "slideright",
    "spin": "radial",
    "glitch": "pixelize",
    "planet_morph": "circleopen",
}


@dataclass(frozen=True)
class Framing:
    """The parts of a clip's chain that depend on its plan: speed curve, crop path or camera."""

    retime: str | None = None
    crop: str | None = None
    camera: str | None = None


NO_FRAMING = Framing()
MAX_PATH_POINTS = 24


def center_crop(aspect: float) -> str:
    return f"crop=w='min(iw,ih*{aspect:.6f})':h='min(ih,iw/{aspect:.6f})'"


def path_crop(path: Sequence[ReframePoint], aspect: float) -> str:
    """A crop that follows the plan's window centers, moving in a straight line between them."""
    points = _thin(path)
    center_x = _piecewise([(point.t, point.x) for point in points])
    center_y = _piecewise([(point.t, point.y) for point in points])
    return (
        f"crop=w='min(iw,ih*{aspect:.6f})':h='min(ih,iw/{aspect:.6f})'"
        f":x='clip(({center_x})*iw-ow/2,0,iw-ow)':y='clip(({center_y})*ih-oh/2,0,ih-oh)'"
    )


def _thin(path: Sequence[ReframePoint]) -> list[ReframePoint]:
    if len(path) <= MAX_PATH_POINTS:
        return list(path)
    step = (len(path) - 1) / (MAX_PATH_POINTS - 1)
    return [path[round(index * step)] for index in range(MAX_PATH_POINTS)]


def _piecewise(points: Sequence[tuple[float, float]]) -> str:
    """Straight lines between (time, value) points, flat before the first and after the last."""
    expression = f"{points[-1][1]:.5f}"
    for (time_a, value_a), (time_b, value_b) in reversed(
        list(zip(points, points[1:], strict=False))
    ):
        if time_b <= time_a:
            continue
        slope = (value_b - value_a) / (time_b - time_a)
        line = f"{value_a:.5f}+({slope:.5f})*(t-{time_a:.4f})"
        expression = f"if(lt(t,{time_b:.4f}),{line},{expression})"
    return f"if(lt(t,{points[0][0]:.4f}),{points[0][1]:.5f},{expression})"


@dataclass(frozen=True)
class StyleFinish:
    """What runs after the transition: style LUT, grain, then motion blur on the moving parts."""

    lut: Path | None = None
    intensity: float = 1.0
    grain: float = 0.0
    blur_amount: float = 0.0
    blur_windows: tuple[tuple[float, float], ...] = ()


def segment_filter(
    effects: Sequence[Effect],
    width: int,
    height: int,
    fps: int,
    sharpen: bool,
    log_lut: Path | None = None,
    framing: Framing = NO_FRAMING,
) -> str:
    """One clip's chain: retime, conform fps, frame to the ratio, effects, finish at the size.

    The retime comes first, so everything after it, the crop path and 360 camera too, works on
    the segment's own timeline. A 360 camera filter ends the chain's first graph and may be a
    split and concat, so only comma-chained filters follow it.
    """
    aspect = width / height
    chain = [f"setpts='{framing.retime}'"] if framing.retime else []
    chain += [f"fps={fps}", f"format={WORK_FORMAT}"]
    if framing.camera:
        chain += [ZERO_TIME, framing.camera]
    else:
        chain.append(framing.crop or center_crop(aspect))
    chain.extend(_motion_filters(effects, width, height))
    if log_lut is not None:
        chain.append(_lut_steps(log_lut, in_matrix=""))
    if sharpen:
        chain.append(SHARPEN)
    chain.extend(_flash(effect) for effect in effects if effect.type == FLASH)
    return ",".join(chain)


def segment_graph(clip: str, finish: StyleFinish) -> str:
    """A segment with a hard cut out. Ends in [out]."""
    return f"[0:v]{clip},{HOLD_LAST_FRAME}{_finish_steps(finish)}[out]"


def transition_graph(
    clip: str,
    next_clip: str,
    transition: str,
    transition_frames: int,
    frames: int,
    fps: int,
    finish: StyleFinish,
) -> str:
    """A segment whose last frames blend into the next clip, ending exactly on the last frame.

    Both streams hold their last frame, so a short source can never cost a frame.
    """
    offset = (frames - transition_frames) / fps
    duration = transition_frames / fps
    return (
        f"[0:v]{clip},{HOLD_LAST_FRAME},{ZERO_TIME}[outgoing];"
        f"[1:v]{next_clip},{HOLD_LAST_FRAME},{ZERO_TIME}[incoming];"
        f"[outgoing][incoming]xfade=transition={transition}"
        f":duration={duration:.6f}:offset={offset:.6f}{_finish_steps(finish)}[out]"
    )


def _finish_steps(finish: StyleFinish) -> str:
    steps = []
    if finish.lut is not None:
        steps.append(_style_grade(finish.lut, finish.intensity))
    if finish.grain > 0:
        steps.append(_grain(finish.grain))
    if finish.blur_amount > 0 and finish.blur_windows:
        steps.append(_motion_blur(finish.blur_amount, finish.blur_windows))
    return "".join(f",{step}" for step in steps)


def _style_grade(lut: Path, intensity: float) -> str:
    """Full strength is the LUT alone; below that it is blended back over the ungraded frame."""
    if intensity >= 1.0:
        return _lut_steps(lut, in_matrix=":in_color_matrix=bt709")
    return (
        f"scale=flags=bicubic:in_color_matrix=bt709,format={RGB_FORMAT},"
        f"split[ungraded][graded];[graded]{_lut3d(lut)}[lut];"
        f"[lut][ungraded]blend=all_mode=normal:all_opacity={intensity:.3f},{_back_to_work_format()}"
    )


def _lut_steps(lut: Path, in_matrix: str) -> str:
    """lut3d works on RGB. Going through it by hand keeps the color matrix under our control."""
    return (
        f"scale=flags=bicubic{in_matrix},format={RGB_FORMAT},{_lut3d(lut)},{_back_to_work_format()}"
    )


def _back_to_work_format() -> str:
    return f"scale=flags=bicubic:out_color_matrix=bt709:out_range=tv,format={WORK_FORMAT}"


def _lut3d(lut: Path) -> str:
    return f"lut3d=file={escape_filter_path(lut)}"


def escape_filter_path(path: Path) -> str:
    """A path for a filter option. FFmpeg unescapes twice: once for the graph, once the option."""
    option = path.as_posix().replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    quoted = option.replace("'", "'\\''")
    return f"'{quoted}'"


def _grain(amount: float) -> str:
    return f"noise=alls={max(1, round(amount * GRAIN_SCALE))}:allf=t"


def _motion_blur(amount: float, windows: Sequence[tuple[float, float]]) -> str:
    """Averages recent frames, like a longer shutter, only while something moves fast.

    tmix must keep running: its own enable option drops frames each time it switches on, so the
    blurred copy is laid over the sharp one instead.
    """
    frames = MOTION_BLUR_MIN_FRAMES + round(min(amount, 1.0) * MOTION_BLUR_EXTRA_FRAMES)
    moving = "+".join(f"between(t,{start:.4f},{end:.4f})" for start, end in windows)
    return (
        f"split[sharp][moving];[moving]tmix=frames={frames}[blurred];"
        f"[sharp][blurred]overlay=format=yuv420p10:enable='{moving}'"
    )


def _motion_filters(effects: Sequence[Effect], width: int, height: int) -> list[str]:
    zooms = [effect for effect in effects if effect.type == ZOOM_PUNCH]
    shakes = [effect for effect in effects if effect.type == SHAKE]
    if not zooms and not shakes:
        return [f"scale={width}:{height}:flags=lanczos"]

    base = 1.0 + SHAKE_OVERSCAN if shakes else 1.0
    zoom = "+".join([f"{base:.3f}", *(_punch(effect) for effect in zooms)])
    offset_x = _shake_offset(shakes, SHAKE_SPEED_X, width)
    offset_y = _shake_offset(shakes, SHAKE_SPEED_Y, height)
    return [
        f"scale=w='2*trunc({width}*({zoom})/2)':h='2*trunc({height}*({zoom})/2)'"
        ":eval=frame:flags=lanczos",
        f"crop={width}:{height}:x='(iw-{width})/2+({offset_x})':y='(ih-{height})/2+({offset_y})'",
    ]


def _punch(effect: Effect) -> str:
    """Jumps up on the hit and eases back to 1 over the effect."""
    return f"{effect.strength or 0.0:.3f}*{_decay(effect)}"


def _shake_offset(shakes: Sequence[Effect], speed: int, size: int) -> str:
    if not shakes:
        return "0"
    reach = SHAKE_MAX_SHARE * size
    return "+".join(
        f"{reach * (effect.strength or 0.0):.2f}*sin(t*{speed})*{_decay(effect)}"
        for effect in shakes
    )


def _decay(effect: Effect) -> str:
    end = effect.at + effect.duration
    return f"between(t,{effect.at:.4f},{end:.4f})*pow(({end:.4f}-t)/{effect.duration:.4f},2)"


def _flash(effect: Effect) -> str:
    end = effect.at + effect.duration
    return (
        f"drawbox=x=0:y=0:w=iw:h=ih:color={FLASH_COLOR}:t=fill"
        f":enable='between(t,{effect.at:.4f},{end:.4f})'"
    )
