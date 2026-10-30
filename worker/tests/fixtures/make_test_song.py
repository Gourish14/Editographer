"""Generates tests/fixtures/test_song.wav: a 24 s, 120 BPM track with a quiet start and a drop.

Beat trackers are trained on real music, so this has what they rely on: a backbeat, a bass line
and chords that change each bar. Run from worker/ with:
uv run python tests/fixtures/make_test_song.py
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 22050
BPM = 120
BARS = 12
BEATS_PER_BAR = 4
DROP_BAR = 6
SEED = 7
FULL_SCALE = 32767
ROOTS_HZ = (110.0, 87.31, 130.81, 98.0)
CHORD_RATIOS = (1.0, 1.2, 1.5)


def tone(frequency: float, length: int, decay: float) -> np.ndarray:
    time = np.arange(length) / SAMPLE_RATE
    return np.sin(2 * np.pi * frequency * time) * np.exp(-time * decay)


def kick(length: int) -> np.ndarray:
    time = np.arange(length) / SAMPLE_RATE
    sweep = 2 * np.pi * (55 * time + 40 * (1 - np.exp(-time * 30)) / 30)
    return np.sin(sweep) * np.exp(-time * 9)


def snare(length: int, rng: np.random.Generator) -> np.ndarray:
    time = np.arange(length) / SAMPLE_RATE
    return (rng.normal(0, 0.6, length) * np.exp(-time * 16)) + tone(190, length, 22) * 0.5


def hat(length: int, rng: np.random.Generator) -> np.ndarray:
    time = np.arange(length) / SAMPLE_RATE
    noise = np.diff(rng.normal(0, 1, length + 1))
    return noise * np.exp(-time * 70) * 0.18


def add(song: np.ndarray, start: int, sound: np.ndarray) -> None:
    end = min(len(song), start + len(sound))
    song[start:end] += sound[: end - start]


def main() -> None:
    rng = np.random.default_rng(SEED)
    beat = int(SAMPLE_RATE * 60 / BPM)
    bar = beat * BEATS_PER_BAR
    song = np.zeros(bar * BARS)

    for bar_index in range(BARS):
        loud = bar_index >= DROP_BAR
        level = 1.0 if loud else 0.32
        root = ROOTS_HZ[bar_index % len(ROOTS_HZ)]
        start = bar_index * bar

        for ratio in CHORD_RATIOS:
            add(song, start, tone(root * 2 * ratio, bar, 1.2) * 0.14 * (1.0 if loud else 0.8))
        for step in range(BEATS_PER_BAR * 2):
            add(song, start + step * beat // 2, hat(beat // 2, rng) * level)
        for index in range(BEATS_PER_BAR):
            position = start + index * beat
            add(song, position, tone(root, beat, 3.0) * 0.35 * level)
            if index % 2 == 0:
                add(song, position, kick(beat) * level)
            else:
                add(song, position, snare(beat, rng) * 0.8 * level)

    pcm = np.clip(song / np.abs(song).max(), -1, 1)
    target = Path(__file__).parent / "test_song.wav"
    with wave.open(str(target), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes((pcm * FULL_SCALE).astype(np.int16).tobytes())


if __name__ == "__main__":
    main()
