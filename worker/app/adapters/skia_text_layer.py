"""Transparent PNG per text item with skia-python. Spec: specs/06-edit-plan-schema.md (text)

SAM 2 text-behind-subject is out of scope: the layer is always drawn in front.
"""

from __future__ import annotations

from pathlib import Path

import skia

from app.domain.brain.text_rules import CAPTION_ANIM, TextItem

CAPTION_CENTER_Y = 0.82
TITLE_CENTER_Y = 0.5
CAPTION_SIZE = 0.05
TITLE_SIZE = 0.09
FONT_FAMILY = "Arial"
MAX_WIDTH_RATIO = 0.9
STROKE_RATIO = 0.08


class SkiaTextLayer:
    def render(self, item: TextItem, width: int, height: int, out: Path) -> Path:
        caption = item.anim == CAPTION_ANIM
        surface = skia.Surface(width, height)
        canvas = surface.getCanvas()
        canvas.clear(skia.ColorTRANSPARENT)
        font = self._fit(
            item.content,
            height * (CAPTION_SIZE if caption else TITLE_SIZE),
            width * MAX_WIDTH_RATIO,
        )
        metrics = font.getMetrics()
        x = (width - font.measureText(item.content)) / 2
        center = CAPTION_CENTER_Y if caption else TITLE_CENTER_Y
        y = height * center - (metrics.fAscent + metrics.fDescent) / 2
        stroke = skia.Paint(
            AntiAlias=True,
            Color=skia.ColorBLACK,
            Style=skia.Paint.kStroke_Style,
            StrokeWidth=font.getSize() * STROKE_RATIO,
        )
        stroke.setStrokeJoin(skia.Paint.kRound_Join)
        fill = skia.Paint(AntiAlias=True, Color=skia.ColorWHITE)
        canvas.drawString(item.content, x, y, font, stroke)
        canvas.drawString(item.content, x, y, font, fill)
        out.parent.mkdir(parents=True, exist_ok=True)
        data = surface.makeImageSnapshot().encodeToData(skia.kPNG, 100)
        if data is None:
            raise OSError(f"Could not encode text layer {out}")
        out.write_bytes(bytes(data))
        return out

    @staticmethod
    def _fit(content: str, size: float, max_width: float) -> skia.Font:
        font = skia.Font(skia.Typeface(FONT_FAMILY, skia.FontStyle.Bold()), size)
        measured = font.measureText(content)
        if measured > max_width:
            font.setSize(size * max_width / measured)
        return font
