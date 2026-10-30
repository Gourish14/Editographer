"""Builds the music map of a song. Spec: specs/04-pipeline.md#stages (2)"""

from __future__ import annotations

from pathlib import Path

from app.domain.brain.music_map import MusicFeatures, build_music_map
from app.domain.errors import AnalysisError, ErrorCode
from app.domain.music import MusicMap
from app.ports.music import AudioCurveExtractor, AudioDecoder, BeatTracker

SAMPLE_RATE = 22050


class AnalyzeMusic:
    def __init__(
        self, decoder: AudioDecoder, tracker: BeatTracker, curves: AudioCurveExtractor
    ) -> None:
        self._decoder = decoder
        self._tracker = tracker
        self._curves = curves

    def run(self, path: Path) -> MusicMap:
        samples = self._decoder.decode_mono(path, SAMPLE_RATE)
        grid = self._tracker.track(samples, SAMPLE_RATE)
        measured = self._curves.extract(samples, SAMPLE_RATE)
        try:
            return build_music_map(
                MusicFeatures(
                    duration_sec=len(samples) / SAMPLE_RATE,
                    beats=grid.beats,
                    downbeats=grid.downbeats,
                    rms=measured.rms,
                    onset_strength=measured.onset_strength,
                    hop_sec=measured.hop_sec,
                )
            )
        except ValueError as error:
            raise AnalysisError(str(error), ErrorCode.ASSET_UNSUPPORTED) from error
