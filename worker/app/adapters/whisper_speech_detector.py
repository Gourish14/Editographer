"""Speech spans and words with faster-whisper small.

Spec: specs/05-editing-brain.md#b8-text-and-audio

CPU int8 by default (no VRAM). With a GpuGuard it runs on CUDA int8_float16 (about 1 GB) while
holding the GPU lock, then frees it.
"""

from __future__ import annotations

from pathlib import Path

import structlog
from faster_whisper import WhisperModel

from app.ports.gpu_guard import GpuGuard
from app.ports.speech import SpeechResult, SpeechSpan, SpokenWord

log = structlog.get_logger()
MAX_NO_SPEECH_PROB = 0.6
MIN_LOGPROB = -1.0


class WhisperSpeechDetector:
    def __init__(self, model_dir: Path, gpu_guard: GpuGuard | None = None) -> None:
        self._model_dir = model_dir
        self._gpu_guard = gpu_guard

    def detect(self, media: Path) -> SpeechResult:
        if self._gpu_guard is None:
            return self._transcribe(self._load("cpu", "int8"), media)
        with self._gpu_guard.loaded(lambda: self._load("cuda", "int8_float16")) as model:
            return self._transcribe(model, media)

    def _load(self, device: str, compute_type: str) -> WhisperModel:
        return WhisperModel(str(self._model_dir), device=device, compute_type=compute_type)

    @staticmethod
    def _transcribe(model: WhisperModel, media: Path) -> SpeechResult:
        segments, _info = model.transcribe(
            str(media), word_timestamps=True, vad_filter=True, condition_on_previous_text=False
        )
        spans: list[SpeechSpan] = []
        words: list[SpokenWord] = []
        for segment in segments:
            if segment.no_speech_prob > MAX_NO_SPEECH_PROB and segment.avg_logprob < MIN_LOGPROB:
                continue
            spans.append(SpeechSpan(round(segment.start, 3), round(segment.end, 3)))
            words.extend(
                SpokenWord(w.word.strip(), round(w.start, 3), round(w.end, 3))
                for w in segment.words or ()
            )
        log.info("speech.detected", media=media.name, spans=len(spans), words=len(words))
        return SpeechResult(tuple(spans), tuple(words))
