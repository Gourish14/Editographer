"""Measures the shots of a clip. Spec: specs/04-pipeline.md#stages (3)

YOLO and CLIP run one after the other, each in its own GPU session, so only one model is ever
on the GPU.
"""

from __future__ import annotations

from pathlib import Path

from app.domain.brain.scoring import describe_shot, measure_shot
from app.domain.brain.shot_tags import TAG_VOCABULARY, tag_phrase
from app.domain.errors import AnalysisError
from app.domain.shots import FrameObjects, FrameSample, ShotMeasure
from app.ports.captioner import Captioner
from app.ports.shots import FrameSampler, ObjectDetector, ShotDetector, ShotEncoder

MAX_CAPTIONED = 40


class AnalyzeShots:
    def __init__(
        self,
        detector: ShotDetector,
        sampler: FrameSampler,
        objects: ObjectDetector,
        encoder: ShotEncoder,
        captioner: Captioner | None = None,
    ) -> None:
        self._detector = detector
        self._sampler = sampler
        self._objects = objects
        self._encoder = encoder
        self._captioner = captioner

    def run(self, proxy: Path, duration_sec: float) -> tuple[ShotMeasure, ...]:
        frames = self._sampler.sample(proxy)
        if not frames:
            raise AnalysisError(f"No frames could be read from {proxy.name}")
        spans = self._detector.detect(proxy) or ((0.0, duration_sec),)
        sampled = [(span, _inside(frames, span)) for span in spans]
        sampled = [(span, inside) for span, inside in sampled if inside]
        if not sampled:
            return ()

        detections = self._objects.detect_objects(proxy)
        visions = self._encoder.encode_shots(proxy, tuple(span for span, _ in sampled))
        phrases = self._encoder.encode_texts(tuple(tag_phrase(tag) for tag in TAG_VOCABULARY))
        vocabulary = dict(zip(TAG_VOCABULARY, phrases, strict=True))
        measures = []
        for (span, inside), vision in zip(sampled, visions, strict=True):
            objects = _inside(detections, span)
            measure = measure_shot(inside, span[0], span[1], objects)
            measures.append(describe_shot(measure, vision, objects, vocabulary))
        return self._captioned(proxy, measures)

    def _captioned(self, proxy: Path, measures: list[ShotMeasure]) -> tuple[ShotMeasure, ...]:
        """Captions only the best shots of the clip (spec 04: top 40); the director sees 40."""
        if self._captioner is None or not measures:
            return tuple(measures)
        best = sorted(range(len(measures)), key=lambda i: _promise(measures[i]), reverse=True)
        chosen = sorted(best[:MAX_CAPTIONED])
        captions = self._captioner.caption_frames(proxy, [measures[i].peak_time for i in chosen])
        for index, caption in zip(chosen, captions, strict=False):
            if caption:
                measures[index] = measures[index].model_copy(update={"caption": caption})
        return tuple(measures)


def _promise(measure: ShotMeasure) -> float:
    return measure.aesthetics + measure.subject + measure.action


def _inside[T: (FrameSample, FrameObjects)](
    items: tuple[T, ...], span: tuple[float, float]
) -> tuple[T, ...]:
    start, end = span
    return tuple(item for item in items if start <= item.time < end)
