"""Beats and downbeats with Beat This!. Spec: specs/09-local-setup.md#6-gb-vram-model-profile"""

from __future__ import annotations

from pathlib import Path

from beat_this.inference import Audio2Beats

from app.ports.music import AudioSamples, BeatGrid

DEVICE = "cpu"


class BeatThisTracker:
    """Runs on the CPU, so it holds no VRAM. The model loads only for the analysis that needs it."""

    def __init__(self, checkpoint: Path) -> None:
        self._checkpoint = checkpoint

    def track(self, samples: AudioSamples, sample_rate: int) -> BeatGrid:
        model = Audio2Beats(checkpoint_path=str(self._checkpoint), device=DEVICE, dbn=False)
        beats, downbeats = model(samples, sample_rate)
        return BeatGrid(
            beats=tuple(round(float(time), 4) for time in beats),
            downbeats=tuple(round(float(time), 4) for time in downbeats),
        )
