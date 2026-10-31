"""Shot captions from Qwen2.5-VL 3B in Ollama.

Spec: specs/05-editing-brain.md#b2-shot-scoring-scoringpy

One frame per shot, a one-sentence answer. The GPU guard is held for the whole clip so no other
model loads; the model stays loaded between that clip's calls and `keep_alive: 0` on the last
call unloads it. Any failure means an empty caption, never a failed job.
"""

from __future__ import annotations

import base64
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import cv2
import httpx
import structlog

from app.ports.gpu_guard import GpuGuard

log = structlog.get_logger()

CAPTION_MODEL = "qwen2.5vl:3b"
PROMPT = "Describe this video frame in one short sentence of at most 15 words. Plain words only."
MAX_EDGE = 448
MAX_CAPTION_CHARS = 120
CONNECT_TIMEOUT_SEC = 2.0
ANSWER_TIMEOUT_SEC = 120.0
KEEP_BETWEEN_CALLS = "1m"


class OllamaCaptioner:
    def __init__(self, client: httpx.Client, gpu: GpuGuard, model: str = CAPTION_MODEL) -> None:
        self._client = client
        self._gpu = gpu
        self._model = model

    @classmethod
    def create(cls, url: str, gpu: GpuGuard, model: str = CAPTION_MODEL) -> OllamaCaptioner:
        timeout = httpx.Timeout(ANSWER_TIMEOUT_SEC, connect=CONNECT_TIMEOUT_SEC)
        return cls(httpx.Client(base_url=url, timeout=timeout), gpu, model)

    def caption_frames(self, path: Path, times: Sequence[float]) -> tuple[str, ...]:
        if not times:
            return ()
        try:
            return self._caption_all(path, times)
        except Exception as error:  # noqa: BLE001 - captions are optional by spec
            log.warning("captioner.failed", clip=path.name, message=str(error))
            return ("",) * len(times)

    def _caption_all(self, path: Path, times: Sequence[float]) -> tuple[str, ...]:
        images = _jpegs(path, times)
        captions: list[str] = []
        with self._gpu.loaded(lambda: self._client):
            for index, image in enumerate(images):
                last = index == len(images) - 1
                captions.append(self._ask(image, last) if image else "")
        return tuple(captions)

    def _ask(self, jpeg: bytes, last: bool) -> str:
        body: dict[str, Any] = {
            "model": self._model,
            "stream": False,
            "keep_alive": 0 if last else KEEP_BETWEEN_CALLS,
            "options": {"temperature": 0, "seed": 1, "num_predict": 48},
            "messages": [
                {
                    "role": "user",
                    "content": PROMPT,
                    "images": [base64.b64encode(jpeg).decode("ascii")],
                }
            ],
        }
        try:
            response = self._client.post("/api/chat", json=body)
            response.raise_for_status()
            text = str(response.json()["message"]["content"])
        except (httpx.HTTPError, KeyError, ValueError) as error:
            log.warning("captioner.call_failed", message=str(error))
            return ""
        return " ".join(text.split())[:MAX_CAPTION_CHARS]


def _jpegs(path: Path, times: Sequence[float]) -> list[bytes | None]:
    capture = cv2.VideoCapture(str(path))
    try:
        found: list[bytes | None] = []
        for time in times:
            capture.set(cv2.CAP_PROP_POS_MSEC, time * 1000.0)
            ok, frame = capture.read()
            found.append(_encode(frame) if ok else None)
        return found
    finally:
        capture.release()


def _encode(frame: Any) -> bytes | None:
    height, width = frame.shape[:2]
    scale = MAX_EDGE / max(height, width)
    if scale < 1:
        frame = cv2.resize(frame, (round(width * scale), round(height * scale)))
    ok, buffer = cv2.imencode(".jpg", frame)
    return bytes(buffer) if ok else None
