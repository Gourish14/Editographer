"""Generates the rehearsal media for the Phase 1 gate: 10 clips and one song.

Spec: specs/10-roadmap.md#phase-1--core-engine [T-118]

Nothing here is real footage. The clips are FFmpeg lavfi patterns with real motion, and the song is
synthesized with what beat trackers rely on: a backbeat, a bass line and chords that change each
bar. Its tempo gives a beat of 15.25 frames at 30 fps on purpose: a tempo that lands on whole frames
would hide rounding drift. numpy is imported where it is used, so tests can load this without it.
"""

from __future__ import annotations

import json
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

SONG_FILE = "song.wav"
TRUTH_FILE = "song_truth.json"
SAMPLE_RATE = 44100
BPM = 118.0
BEATS_PER_BAR = 4
SEED = 118
FULL_SCALE = 32767
PEAK = 0.89
ROOTS_HZ = (110.0, 87.31, 130.81, 98.0)
CHORD_RATIOS = (1.0, 1.2, 1.5)
ARPEGGIO_RATIOS = (1.0, 1.5, 2.0, 2.4)
STEREO_SPREAD = 0.35


@dataclass(frozen=True)
class SongPart:
    kind: str
    bars: int
    level: float
    four_on_floor: bool = False
    arpeggio: bool = False
    riser: bool = False


SONG_PARTS = (
    SongPart("intro", 8, 0.3),
    SongPart("build", 8, 0.5, riser=True),
    SongPart("drop", 12, 1.0, four_on_floor=True, arpeggio=True),
    SongPart("break", 6, 0.22, arpeggio=True),
    SongPart("build", 4, 0.55, riser=True),
    SongPart("drop", 12, 1.0, four_on_floor=True, arpeggio=True),
    SongPart("outro", 4, 0.3),
)


@dataclass(frozen=True)
class ClipSpec:
    name: str
    width: int
    height: int
    fps: int
    seconds: float
    encoder: str
    graph: str
    hard_cut_at: float | None = None


H264 = "h264"
HEVC_10_BIT = "hevc10"


def moving_shapes(base: str, width: int, height: int, count: int = 3) -> str:
    """Solid shapes that bounce across a labelled base stream and end as [out]."""
    colors = ("orange", "cyan", "magenta", "yellow")
    size = height // 5
    parts = []
    current = base
    for index in range(count):
        speed_x = 1.3 + index * 0.9
        speed_y = 2.1 + index * 0.7
        parts.append(f"color=c={colors[index % len(colors)]}:s={size}x{size}[shape{index}]")
        parts.append(
            f"[{current}][shape{index}]overlay="
            f"x='(W-w)/2+(W-w)/2*sin(t*{speed_x:.1f})':y='(H-h)/2+(H-h)/2*cos(t*{speed_y:.1f})'"
            f":shortest=1[mix{index}]"
        )
        current = f"mix{index}"
    parts.append(f"[{current}]null[out]")
    return ";".join(parts)


def hard_cut(first: str, second: str, cut_at: float, seconds: float, fps: int) -> str:
    """Two sources joined with one hard cut, ending as [out]."""
    return (
        f"{first},fps={fps},format=yuv420p,trim=duration={cut_at},setpts=PTS-STARTPTS[one];"
        f"{second},fps={fps},format=yuv420p,trim=duration={seconds - cut_at},"
        f"setpts=PTS-STARTPTS[two];[one][two]concat=n=2:v=1[out]"
    )


def clip_specs() -> tuple[ClipSpec, ...]:
    """Ten clips that differ in size, frame rate, codec, bit depth and kind of motion."""
    return (
        ClipSpec(
            "01_orbit_4k30_hevc10.mp4", 3840, 2160, 30, 18.0, HEVC_10_BIT,
            "testsrc2=s=3840x2160:r=30,hue=H=0.4*t[base];" + moving_shapes("base", 3840, 2160),
        ),
        ClipSpec(
            "02_fractal_1080p60_h264.mp4", 1920, 1080, 60, 16.0, H264,
            "mandelbrot=s=960x540:r=60:maxiter=256,scale=1920:1080:flags=lanczos[out]",
        ),
        ClipSpec(
            "03_cells_4k30_hevc10.mp4", 3840, 2160, 30, 16.0, HEVC_10_BIT,
            "life=s=480x270:r=30:mold=25:ratio=0.2:life_color=#40ff80:death_color=#c83232,"
            "scale=3840:2160:flags=neighbor[out]",
        ),
        ClipSpec(
            "04_gradient_1080p30_h264.mp4", 1920, 1080, 30, 20.0, H264,
            "gradients=s=1920x1080:r=30:c0=#e04040:c1=#3040e0:c2=#40c060:n=3:speed=0.03,"
            "format=yuv420p,noise=alls=10:allf=t[base];" + moving_shapes("base", 1920, 1080),
        ),
        ClipSpec(
            "05_hardcut_bars_1080p24_h264.mp4", 1920, 1080, 24, 18.0, H264,
            hard_cut(
                "smptehdbars=s=1920x1080:r=24,scroll=h=0.004",
                "testsrc2=s=1920x1080:r=24",
                9.0, 18.0, 24,
            ),
            hard_cut_at=9.0,
        ),
        ClipSpec(
            "06_hardcut_grid_4k60_hevc10.mp4", 3840, 2160, 60, 16.0, HEVC_10_BIT,
            hard_cut(
                "color=c=#102040:s=3840x2160:r=60,drawgrid=w=160:h=160:t=6:c=white,"
                "scroll=h=0.003:v=0.002",
                "testsrc2=s=3840x2160:r=60,hue=s=2",
                7.0, 16.0, 60,
            ),
            hard_cut_at=7.0,
        ),
        ClipSpec(
            "07_grid_pan_4k30_hevc10.mp4", 3840, 2160, 30, 20.0, HEVC_10_BIT,
            "color=c=#203820:s=3840x2160:r=30,drawgrid=w=120:h=120:t=5:c=#f0e0a0,"
            "scroll=h=0.0025:v=0.001[base];" + moving_shapes("base", 3840, 2160, 2),
        ),
        ClipSpec(
            "08_vertical_1080p30_h264.mp4", 1080, 1920, 30, 16.0, H264,
            "testsrc2=s=1080x1920:r=30[base];" + moving_shapes("base", 1080, 1920),
        ),
        ClipSpec(
            "09_dim_shapes_1080p60_h264.mp4", 1920, 1080, 60, 15.0, H264,
            "color=c=#181820:s=1920x1080:r=60,noise=alls=8:allf=t[base];"
            + moving_shapes("base", 1920, 1080, 4),
        ),
        ClipSpec(
            "10_rule_4k24_hevc10.mp4", 3840, 2160, 24, 15.0, HEVC_10_BIT,
            "cellauto=s=640x360:r=24:rule=110:ratio=0.5:scroll=1,"
            "scale=3840:2160:flags=neighbor,hue=H=t[out]",
        ),
    )  # fmt: skip


def clip_command(spec: ClipSpec, target: Path) -> list[str]:
    """The FFmpeg arguments that write one clip."""
    return [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-filter_complex", _finished_graph(spec),
        "-map", "[video]",
        "-t", f"{spec.seconds:g}",
        *_encoder_arguments(spec.encoder),
        str(target),
    ]  # fmt: skip


def _finished_graph(spec: ClipSpec) -> str:
    pixel_format = "p010le" if spec.encoder == HEVC_10_BIT else "yuv420p"
    return f"{spec.graph};[out]format={pixel_format}[video]"


def _encoder_arguments(encoder: str) -> list[str]:
    if encoder == HEVC_10_BIT:
        return ["-c:v", "hevc_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "24", "-b:v", "0",
                "-profile:v", "main10"]  # fmt: skip
    return ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "23", "-b:v", "0"]


def generate_clips(folder: Path) -> list[Path]:
    """Writes every clip that does not exist yet and returns all their paths."""
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for spec in clip_specs():
        target = folder / spec.name
        if not target.exists():
            partial = target.with_name(f"partial_{spec.name}")
            subprocess.run(clip_command(spec, partial), check=True)
            partial.replace(target)
        paths.append(target)
    return paths


def beat_seconds() -> float:
    return 60.0 / BPM


def song_truth() -> dict[str, object]:
    """Where the beats really are, which no tracker can get wrong."""
    beat = beat_seconds()
    total_bars = sum(part.bars for part in SONG_PARTS)
    beats = [round(index * beat, 6) for index in range(total_bars * BEATS_PER_BAR + 1)]
    sections = []
    bar = 0
    for part in SONG_PARTS:
        sections.append(
            {
                "kind": part.kind,
                "start": round(bar * BEATS_PER_BAR * beat, 6),
                "end": round((bar + part.bars) * BEATS_PER_BAR * beat, 6),
            }
        )
        bar += part.bars
    return {
        "bpm": BPM,
        "beats": beats,
        "downbeats": beats[::BEATS_PER_BAR],
        "sections": sections,
    }


def generate_song(folder: Path) -> Path:
    """Writes the song and its beat truth unless they exist, and returns the song path."""
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / SONG_FILE
    truth = folder / TRUTH_FILE
    if target.exists() and truth.exists():
        return target
    _write_stereo(target, _mix_song())
    truth.write_text(json.dumps(song_truth(), indent=1), encoding="utf-8")
    return target


def _write_stereo(target: Path, song: object) -> None:
    import numpy as np

    samples = np.asarray(song)
    scaled = np.clip(samples / np.abs(samples).max() * PEAK, -1, 1)
    with wave.open(str(target), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes((scaled * FULL_SCALE).astype(np.int16).tobytes())


def _mix_song() -> object:
    """Stereo samples, shape (frames, 2). Sections differ in level and in what plays."""
    import numpy as np

    rng = np.random.default_rng(SEED)
    beat = beat_seconds()
    bar_sec = beat * BEATS_PER_BAR
    total_bars = sum(part.bars for part in SONG_PARTS)
    length = round((total_bars + 1) * bar_sec * SAMPLE_RATE)
    center = np.zeros(length)
    left = np.zeros(length)
    right = np.zeros(length)

    def at(seconds: float) -> int:
        return round(seconds * SAMPLE_RATE)

    def add(track: np.ndarray, start: int, sound: np.ndarray) -> None:
        end = min(len(track), start + len(sound))
        track[start:end] += sound[: end - start]

    def time_axis(seconds: float) -> np.ndarray:
        return np.arange(at(seconds)) / SAMPLE_RATE

    def tone(frequency: float, seconds: float, decay: float) -> np.ndarray:
        time = time_axis(seconds)
        wave_form = np.sin(2 * np.pi * frequency * time)
        wave_form += 0.4 * np.sin(4 * np.pi * frequency * time)
        wave_form += 0.2 * np.sin(6 * np.pi * frequency * time)
        return wave_form * np.exp(-time * decay)

    def kick() -> np.ndarray:
        time = time_axis(beat)
        sweep = 2 * np.pi * (52 * time + 45 * (1 - np.exp(-time * 30)) / 30)
        return np.sin(sweep) * np.exp(-time * 8)

    def snare() -> np.ndarray:
        time = time_axis(beat)
        return rng.normal(0, 0.6, len(time)) * np.exp(-time * 15) + tone(190, beat, 22) * 0.4

    def hat() -> np.ndarray:
        time = time_axis(beat / 2)
        return np.diff(rng.normal(0, 1, len(time) + 1)) * np.exp(-time * 60) * 0.16

    bar_index = 0
    for part in SONG_PARTS:
        for part_bar in range(part.bars):
            start = bar_index * bar_sec
            root = ROOTS_HZ[bar_index % len(ROOTS_HZ)]
            for voice, ratio in enumerate(CHORD_RATIOS):
                pad = tone(root * 2 * ratio, bar_sec, 1.1) * 0.13
                add(left, at(start), pad * (1 + STEREO_SPREAD * (voice - 1)))
                add(right, at(start), pad * (1 - STEREO_SPREAD * (voice - 1)))
            for step in range(BEATS_PER_BAR * 2):
                add(center, at(start + step * beat / 2), hat() * part.level)
            for index in range(BEATS_PER_BAR):
                position = start + index * beat
                add(center, at(position), tone(root, beat, 3.0) * 0.32 * part.level)
                add(center, at(position + beat / 2), tone(root, beat / 2, 6.0) * 0.2 * part.level)
                if part.four_on_floor or index % 2 == 0:
                    add(center, at(position), kick() * part.level)
                if index % 2 == 1:
                    add(center, at(position), snare() * 0.8 * part.level)
                if part.riser and part_bar >= part.bars - 2:
                    add(center, at(position + beat / 2), snare() * 0.35 * part.level)
            if part.arpeggio:
                for step in range(BEATS_PER_BAR * 4):
                    ratio = ARPEGGIO_RATIOS[step % len(ARPEGGIO_RATIOS)]
                    note = tone(root * 4 * ratio, beat / 2, 9.0) * 0.1 * max(part.level, 0.5)
                    pan = 1 if step % 2 == 0 else -1
                    position = at(start + step * beat / 4)
                    add(left, position, note * (1 + STEREO_SPREAD * pan))
                    add(right, position, note * (1 - STEREO_SPREAD * pan))
            if part.riser:
                time = time_axis(bar_sec)
                progress = (part_bar + time / bar_sec) / part.bars
                noise = np.diff(rng.normal(0, 1, len(time) + 1)) * progress**2 * 0.05
                add(left, at(start), noise)
                add(right, at(start), noise)
            bar_index += 1
    return np.stack((center + left, center + right), axis=1)
