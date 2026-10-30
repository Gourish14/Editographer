"""Generates tests/fixtures/test_song.wav: 20 s at 120 BPM with a quiet start and a loud drop.

Run from worker/ with: uv run python tests/fixtures/make_test_song.py
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 22050
BPM = 120
DURATION_SEC = 20
DROP_SEC = 10
SEED = 7
FULL_SCALE = 32767


def kick(length: int) -> np.ndarray:
    time = np.arange(length) / SAMPLE_RATE
    return np.sin(2 * np.pi * 70 * time) * np.exp(-time * 18)


def hat(length: int, rng: np.random.Generator) -> np.ndarray:
    time = np.arange(length) / SAMPLE_RATE
    return rng.normal(0, 1, length) * np.exp(-time * 60) * 0.25


def main() -> None:
    rng = np.random.default_rng(SEED)
    total = SAMPLE_RATE * DURATION_SEC
    beat = int(SAMPLE_RATE * 60 / BPM)
    song = np.zeros(total)
    for index in range(total // beat):
        start = index * beat
        level = 0.25 if start < DROP_SEC * SAMPLE_RATE else 1.0
        accent = 1.0 if index % 4 == 0 else 0.7
        song[start : start + beat] += kick(beat)[: total - start] * level * accent
        offbeat = start + beat // 2
        if offbeat + beat // 2 <= total:
            song[offbeat : offbeat + beat // 2] += hat(beat // 2, rng) * level
    time = np.arange(total) / SAMPLE_RATE
    song += np.where(time >= DROP_SEC, 0.3, 0.06) * np.sin(2 * np.pi * 110 * time)
    pcm = np.clip(song / np.abs(song).max(), -1, 1)

    target = Path(__file__).parent / "test_song.wav"
    with wave.open(str(target), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes((pcm * FULL_SCALE).astype(np.int16).tobytes())


if __name__ == "__main__":
    main()
