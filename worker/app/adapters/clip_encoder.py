"""OpenCLIP ViT-B/32 embeddings and LAION aesthetics. Spec: specs/05-editing-brain.md#b2

The weights are OpenAI's, because the LAION aesthetic head was trained on their embeddings.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import batched
from pathlib import Path
from typing import Any

import cv2
import torch
from PIL import Image

from app.adapters.model_runtime import (
    best_device,
    gpu_errors,
    pin_model_folders,
    require_file,
)
from app.adapters.proxy_frames import sampled_frames
from app.domain.shots import Embedding, ShotVision
from app.ports.gpu_guard import GpuGuard

MODEL_NAME = "ViT-B-32-quickgelu"
EMBEDDING_SIZE = 512
BATCH_FRAMES = 32
EMBEDDING_DECIMALS = 5
AESTHETIC_MIN = 1.0
AESTHETIC_MAX = 10.0


@dataclass
class _Runtime:
    model: Any
    aesthetic: torch.nn.Linear
    preprocess: Any
    tokenizer: Any
    device: str


@dataclass
class _ShotTotal:
    """Running sums, so a long shot costs no more memory than a short one."""

    embedding: torch.Tensor
    aesthetics: float = 0.0
    frames: int = 0


class OpenClipEncoder:
    def __init__(self, weights: Path, aesthetic_weights: Path, gpu: GpuGuard) -> None:
        self._weights = weights
        self._aesthetic_weights = aesthetic_weights
        self._gpu = gpu
        self._texts: dict[str, Embedding] = {}

    def encode_shots(
        self, path: Path, spans: Sequence[tuple[float, float]]
    ) -> tuple[ShotVision, ...]:
        with gpu_errors(), self._gpu.loaded(self._load) as runtime:
            try:
                return _encode_shots(runtime, path, spans)
            finally:
                del runtime  # the guard frees VRAM on exit, so nothing may still hold the model

    def encode_texts(self, texts: Sequence[str]) -> tuple[Embedding, ...]:
        """Phrases repeat for every clip, so each one reaches the GPU only once."""
        missing = [text for text in dict.fromkeys(texts) if text not in self._texts]
        if missing:
            with gpu_errors(), self._gpu.loaded(self._load) as runtime:
                try:
                    self._texts.update(zip(missing, _encode_texts(runtime, missing), strict=True))
                finally:
                    del runtime
        return tuple(self._texts[text] for text in texts)

    def _load(self) -> _Runtime:
        pin_model_folders(self._weights.parent.parent)
        import open_clip

        device = best_device()
        model, _, preprocess = open_clip.create_model_and_transforms(
            MODEL_NAME, pretrained=str(require_file(self._weights)), device=device
        )
        model.eval()
        aesthetic = torch.nn.Linear(EMBEDDING_SIZE, 1)
        state = torch.load(require_file(self._aesthetic_weights), weights_only=True)
        aesthetic.load_state_dict(state)
        aesthetic.to(device).eval()
        return _Runtime(model, aesthetic, preprocess, open_clip.get_tokenizer(MODEL_NAME), device)


@torch.inference_mode()
def _encode_shots(
    runtime: _Runtime, path: Path, spans: Sequence[tuple[float, float]]
) -> tuple[ShotVision, ...]:
    totals = [_ShotTotal(torch.zeros(EMBEDDING_SIZE)) for _ in spans]
    starts = [start for start, _ in spans]
    inside = (
        (index, frame)
        for time, frame in sampled_frames(path)
        if (index := _span_of(time, spans, starts)) is not None
    )
    for batch in batched(inside, BATCH_FRAMES):
        images = torch.stack([runtime.preprocess(_to_image(frame)) for _, frame in batch])
        embeddings = _unit(_autocast(runtime, runtime.model.encode_image, images))
        scores = runtime.aesthetic(embeddings).squeeze(1).tolist()
        for (index, _), embedding, score in zip(batch, embeddings.cpu(), scores, strict=True):
            total = totals[index]
            total.embedding += embedding
            total.aesthetics += _scaled(score)
            total.frames += 1
    return tuple(_vision(total) for total in totals)


@torch.inference_mode()
def _encode_texts(runtime: _Runtime, texts: Sequence[str]) -> list[Embedding]:
    tokens = runtime.tokenizer(list(texts))
    embeddings = _unit(_autocast(runtime, runtime.model.encode_text, tokens))
    return [_plain(embedding) for embedding in embeddings.cpu()]


def _autocast(runtime: _Runtime, encode: Any, batch: torch.Tensor) -> torch.Tensor:
    """fp16 halves the VRAM; the cast back keeps the aesthetic head's float32 input."""
    with torch.autocast(runtime.device):
        return encode(batch.to(runtime.device)).float()


def _span_of(
    time: float, spans: Sequence[tuple[float, float]], starts: Sequence[float]
) -> int | None:
    """Which span holds this time. Spans are in order and do not overlap."""
    index = bisect_right(starts, time) - 1
    return index if index >= 0 and time < spans[index][1] else None


def _to_image(frame: Any) -> Image.Image:
    return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))


def _unit(vectors: torch.Tensor) -> torch.Tensor:
    return torch.nn.functional.normalize(vectors, dim=-1)


def _scaled(score: float) -> float:
    return min(1.0, max(0.0, (score - AESTHETIC_MIN) / (AESTHETIC_MAX - AESTHETIC_MIN)))


def _vision(total: _ShotTotal) -> ShotVision:
    if not total.frames:
        return ShotVision((), 0.0)
    embedding = _plain(_unit(total.embedding))
    return ShotVision(embedding, round(total.aesthetics / total.frames, 4))


def _plain(vector: torch.Tensor) -> Embedding:
    return tuple(round(value, EMBEDDING_DECIMALS) for value in vector.tolist())
