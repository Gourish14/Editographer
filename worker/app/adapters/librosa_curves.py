"""Loudness and onset curves with librosa. Spec: specs/04-pipeline.md#stages (2)"""

from __future__ import annotations

import librosa

from app.ports.music import AudioCurves, AudioSamples

HOP_LENGTH = 512
FRAME_LENGTH = 2048


class LibrosaCurveExtractor:
    def extract(self, samples: AudioSamples, sample_rate: int) -> AudioCurves:
        rms = librosa.feature.rms(y=samples, frame_length=FRAME_LENGTH, hop_length=HOP_LENGTH)[0]
        onset = librosa.onset.onset_strength(y=samples, sr=sample_rate, hop_length=HOP_LENGTH)
        return AudioCurves(
            rms=tuple(float(value) for value in rms),
            onset_strength=tuple(float(value) for value in onset),
            hop_sec=HOP_LENGTH / sample_rate,
        )
