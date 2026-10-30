"""Builds FFmpeg filter graphs for a segment. Spec: specs/04-pipeline.md#stages (6)

Pure text building, so it can be tested without FFmpeg. crop cannot change size per frame, so a
zoom scales up per frame and then crops back to the output size. crop reads iw and ih only once,
so its offsets repeat the scale size expression instead of trusting them.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.brain.effects import FLASH, SHAKE, ZOOM_PUNCH
from app.domain.plan import Effect

SHAKE_OVERSCAN = 0.04
SHAKE_MAX_SHARE = 0.015
SHAKE_SPEED_X = 71
SHAKE_SPEED_Y = 53
FLASH_COLOR = "white@0.85"
SHARPEN = "unsharp=5:5:0.6"
WORK_FORMAT = "yuv420p10le"


def segment_filter(
    effects: Sequence[Effect], width: int, height: int, fps: int, sharpen: bool
) -> str:
    """The -vf chain: conform fps, crop to the ratio, apply effects, finish at the output size."""
    aspect = width / height
    chain = [
        f"fps={fps}",
        f"format={WORK_FORMAT}",
        f"crop=w='min(iw,ih*{aspect:.6f})':h='min(ih,iw/{aspect:.6f})'",
    ]
    chain.extend(_motion_filters(effects, width, height))
    if sharpen:
        chain.append(SHARPEN)
    chain.extend(_flash(effect) for effect in effects if effect.type == FLASH)
    return ",".join(chain)


def _motion_filters(effects: Sequence[Effect], width: int, height: int) -> list[str]:
    zooms = [effect for effect in effects if effect.type == ZOOM_PUNCH]
    shakes = [effect for effect in effects if effect.type == SHAKE]
    if not zooms and not shakes:
        return [f"scale={width}:{height}:flags=lanczos"]

    base = 1.0 + SHAKE_OVERSCAN if shakes else 1.0
    zoom = "+".join([f"{base:.3f}", *(_punch(effect) for effect in zooms)])
    offset_x = _shake_offset(shakes, SHAKE_SPEED_X, width)
    offset_y = _shake_offset(shakes, SHAKE_SPEED_Y, height)
    scaled_width = f"2*trunc({width}*({zoom})/2)"
    scaled_height = f"2*trunc({height}*({zoom})/2)"
    return [
        f"scale=w='{scaled_width}':h='{scaled_height}':eval=frame:flags=lanczos",
        f"crop={width}:{height}"
        f":x='({scaled_width}-{width})/2+({offset_x})'"
        f":y='({scaled_height}-{height})/2+({offset_y})'",
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
