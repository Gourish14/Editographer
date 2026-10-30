"""The final mix. Spec: specs/04-pipeline.md#stages (8), specs/05-editing-brain.md#b8

Music is leveled first, so SFX sit at their gain against music at -14 LUFS however loud the song
was. The whole mix is then measured and trimmed, so what the listener gets is -14 LUFS.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyloudnorm
import structlog

from app.adapters.ffmpeg_runner import FfmpegError, run_tool, run_tool_for_bytes
from app.config import ROOT
from app.domain.errors import RenderError
from app.domain.look import SPEECH_DUCK_DB
from app.ports.render import MUSIC_ONLY, AudioMix, KeptClipAudio, SfxPlacement

log = structlog.get_logger()

TARGET_LUFS = -14.0
SAMPLE_RATE = 48000
CHANNELS = 2
AUDIO_BITRATE = "320k"
LIMIT = 0.97
LEVELING_PASSES = 3
CLOSE_ENOUGH_LU = 0.2
DUCK_RAMP_SEC = 0.05
BASE_ARGUMENTS = ("ffmpeg", "-hide_banner", "-loglevel", "error")
CONFORM = f"aresample={SAMPLE_RATE},aformat=channel_layouts=stereo"


@dataclass(frozen=True)
class _Sources:
    """The mix's inputs, after the music. Each SFX file is one input however often it plays."""

    sfx: tuple[tuple[Path, tuple[SfxPlacement, ...]], ...]
    speech: tuple[KeptClipAudio, ...]

    @property
    def has_mix(self) -> bool:
        return bool(self.sfx or self.speech)

    def input_arguments(self) -> list[str]:
        arguments: list[str] = []
        for path, _ in self.sfx:
            arguments += ["-i", str(path)]
        for clip in self.speech:
            arguments += [
                "-ss",
                f"{clip.src_in:.4f}",
                "-t",
                f"{clip.duration:.4f}",
                "-i",
                str(clip.source),
            ]
        return arguments


class FfmpegAudioFinisher:
    def __init__(self, sfx_dir: Path = ROOT / "sfx") -> None:
        self._sfx_dir = sfx_dir

    def add_music(
        self,
        video: Path,
        music: Path,
        start: float,
        duration: float,
        target: Path,
        mix: AudioMix = MUSIC_ONLY,
    ) -> None:
        window = ["-ss", f"{start:.4f}", "-t", f"{duration:.4f}", "-i", str(music)]
        sources = _Sources(self._sfx_files(mix.sfx), mix.speech)
        inputs = [*window, *sources.input_arguments()]
        try:
            music_gain = _gain_to_target(
                window, lambda gain: mix_graph(_Sources((), ()), 0, gain, 0.0)
            )
            trim = 0.0
            if sources.has_mix:
                trim = _gain_to_target(inputs, lambda gain: mix_graph(sources, 0, music_gain, gain))
            run_tool(
                [
                    *BASE_ARGUMENTS,
                    "-y",
                    "-i",
                    str(video),
                    *inputs,
                    "-filter_complex",
                    mix_graph(sources, 1, music_gain, trim),
                    "-map",
                    "0:v:0",
                    "-map",
                    "[out]",
                    "-ac",
                    str(CHANNELS),
                    "-ar",
                    str(SAMPLE_RATE),
                    "-c:v",
                    "copy",
                    "-c:a",
                    "aac",
                    "-b:a",
                    AUDIO_BITRATE,
                    "-movflags",
                    "+faststart",
                    "-shortest",
                    str(target),
                ]
            )
        except FfmpegError as error:
            raise RenderError(str(error)) from error

    def _sfx_files(
        self, cues: Sequence[SfxPlacement]
    ) -> tuple[tuple[Path, tuple[SfxPlacement, ...]], ...]:
        """Groups cues by file. A missing file is skipped: the edit is worth more than one hit."""
        by_type: defaultdict[str, list[SfxPlacement]] = defaultdict(list)
        for cue in cues:
            by_type[cue.type].append(cue)
        found = []
        for kind, placed in by_type.items():
            path = self._sfx_dir / f"{kind}.wav"
            if path.is_file():
                found.append((path, tuple(placed)))
            else:
                log.warning("render.sfx_missing", sfx=kind)
        return tuple(found)


def mix_graph(sources: _Sources, music_input: int, music_gain: float, trim_db: float) -> str:
    """The filter graph, ending in [out]. music_input is 0 when measuring, 1 next to the video."""
    steps = [
        f"[{music_input}:a]asetpts=PTS-STARTPTS,{CONFORM},"
        f"{duck_filter(sources.speech)}{_level_filter(music_gain)}[music]"
    ]
    labels = ["[music]"]
    next_input = music_input + 1
    for path_index, (_, placed) in enumerate(sources.sfx):
        step, cue_labels = _sfx_steps(next_input, path_index, placed)
        steps.append(step)
        labels += cue_labels
        next_input += 1
    for index, clip in enumerate(sources.speech):
        delay = round(clip.at * SAMPLE_RATE)
        steps.append(f"[{next_input}:a]{CONFORM},adelay=delays={delay}S:all=1[speech{index}]")
        labels.append(f"[speech{index}]")
        next_input += 1
    if len(labels) == 1:
        steps[0] = steps[0].replace("[music]", "[out]")
    else:
        steps.append(
            f"{''.join(labels)}amix=inputs={len(labels)}:duration=first:normalize=0,"
            f"{_level_filter(trim_db)}[out]"
        )
    return ";".join(steps)


def _sfx_steps(
    input_index: int, file_index: int, placed: Sequence[SfxPlacement]
) -> tuple[str, list[str]]:
    copies = [f"[copy{file_index}x{index}]" for index in range(len(placed))]
    labels = [f"[sfx{file_index}x{index}]" for index in range(len(placed))]
    steps = [f"[{input_index}:a]{CONFORM},asplit={len(placed)}{''.join(copies)}"]
    for copy, label, cue in zip(copies, labels, placed, strict=True):
        delay = max(0, round(cue.at * SAMPLE_RATE))
        steps.append(f"{copy}adelay=delays={delay}S:all=1,volume={cue.gain_db:.2f}dB{label}")
    return ";".join(steps), labels


def duck_filter(speech: Sequence[KeptClipAudio]) -> str:
    """B8: music sits 8 dB down while clip audio is kept, with short ramps outside the window."""
    if not speech:
        return ""
    windows = "+".join(_window(clip) for clip in speech)
    return f"volume=volume='pow(10,-{SPEECH_DUCK_DB}*min(1,{windows})/20)':eval=frame,"


def _window(clip: KeptClipAudio) -> str:
    rise = clip.at - DUCK_RAMP_SEC
    fall = clip.at + clip.duration + DUCK_RAMP_SEC
    return f"clip((t-{rise:.4f})/{DUCK_RAMP_SEC},0,1)*clip(({fall:.4f}-t)/{DUCK_RAMP_SEC},0,1)"


def _level_filter(gain_db: float) -> str:
    return f"volume={gain_db:.2f}dB,alimiter=limit={LIMIT}:level=disabled"


def _gain_to_target(inputs: list[str], graph_for: Callable[[float], str]) -> float:
    """The limiter takes back some of any boost, so measure after it and correct."""
    gain_db = 0.0
    for _ in range(LEVELING_PASSES):
        loudness = _measure(inputs, graph_for(gain_db))
        if not math.isfinite(loudness):
            return gain_db
        difference = TARGET_LUFS - loudness
        gain_db += difference
        if abs(difference) <= CLOSE_ENOUGH_LU:
            break
    return gain_db


def _measure(inputs: list[str], graph: str) -> float:
    raw = run_tool_for_bytes(
        [
            *BASE_ARGUMENTS,
            *inputs,
            "-filter_complex",
            graph,
            "-map",
            "[out]",
            "-ac",
            str(CHANNELS),
            "-ar",
            str(SAMPLE_RATE),
            "-f",
            "f32le",
            "-",
        ]
    )
    samples = np.frombuffer(raw, dtype=np.float32).reshape(-1, CHANNELS)
    return float(pyloudnorm.Meter(SAMPLE_RATE).integrated_loudness(samples))
