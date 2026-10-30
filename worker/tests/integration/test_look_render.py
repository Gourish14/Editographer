"""Real FFmpeg and NVENC renders of the look and the mix.

Spec: specs/04-pipeline.md#stages (6, 8), specs/05-editing-brain.md#b5 #b8 [T-303]
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pyloudnorm
import pytest

from app.adapters.ffmpeg_audio_finisher import SAMPLE_RATE, FfmpegAudioFinisher
from app.adapters.ffmpeg_compositor import DJI_LOG_LUT, FfmpegCompositor
from app.adapters.ffmpeg_filters import XFADE_BY_TRANSITION
from app.domain.plan import Effect, Grade, Segment, Source, Transition
from app.ports.render import (
    AudioMix,
    EncodeProfile,
    KeptClipAudio,
    NextClip,
    SegmentLook,
    SfxPlacement,
)

pytestmark = [
    pytest.mark.gpu,
    pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs FFmpeg"),
]

WIDTH, HEIGHT, FPS = 320, 180, 30
FRAMES = 30
PROFILE = EncodeProfile(WIDTH, HEIGHT, FPS, 24, "p2", False)
PLAIN = Source(camera_mode=None, log_profile=None, native_fps=30)
LOG = Source(camera_mode=None, log_profile="DLOGM", native_fps=30)
Pixels = npt.NDArray[np.float64]
Audio = npt.NDArray[np.float32]


def ffmpeg(*arguments: str | Path) -> None:
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *map(str, arguments)], check=True
    )


def color_clip(target: Path, color: str, seconds: int = 3) -> Path:
    ffmpeg(
        "-f", "lavfi", "-i", f"color=c={color}:s=640x360:r=30:d={seconds}",
        "-colorspace", "bt709", "-c:v", "libx264", "-pix_fmt", "yuv420p", target,
    )  # fmt: skip
    return target


def frame_count(path: Path) -> int:
    output = subprocess.run(
        [
            "ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
            "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(path),
        ],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    return int(output.stdout.strip().strip(","))


def frame_rgb(path: Path, index: int) -> Pixels:
    """Mean color of one frame, 0 to 255."""
    output = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path),
            "-vf", f"select=eq(n\\,{index}),scale=out_color_matrix=bt709",
            "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
        ],
        capture_output=True, check=True,
    )  # fmt: skip
    return np.frombuffer(output.stdout, dtype=np.uint8).reshape(-1, 3).astype(np.float64)


def cube(path: Path, map_rgb: str) -> Path:
    """A 2-point LUT: 'swap' turns red into blue, 'half' halves everything."""
    rows = []
    for blue in (0, 1):
        for green in (0, 1):
            for red in (0, 1):
                mapped = {"swap": (blue, green, red), "half": (red / 2, green / 2, blue / 2)}
                rows.append(" ".join(f"{value:.3f}" for value in mapped[map_rgb]))
    path.write_text("LUT_3D_SIZE 2\n" + "\n".join(rows) + "\n", encoding="ascii")
    return path


def seg(**fields: object) -> Segment:
    values: dict[str, object] = {
        "id": "s",
        "asset_id": "a",
        "type": "video",
        "src_in": 0.5,
        "src_out": 1.5,
        "at": 0.0,
        "duration": 1.0,
        "source": PLAIN,
    }
    return Segment.model_validate(values | fields)


@pytest.fixture(scope="module")
def clips(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    folder = tmp_path_factory.mktemp("look")
    return {
        "red": color_clip(folder / "red.mp4", "red"),
        "blue": color_clip(folder / "blue.mp4", "blue"),
        "short": color_clip(folder / "short.mp4", "green", 1),
    }


@pytest.mark.parametrize("kind", sorted(XFADE_BY_TRANSITION))
def test_b5_every_transition_keeps_the_exact_frame_count_and_ends_on_the_next_clip(
    clips: dict[str, Path], tmp_path: Path, kind: str
) -> None:
    out = tmp_path / "out.mp4"
    segment = seg(transition_out=Transition(type=kind, duration=0.2))
    look = SegmentLook(next_clip=NextClip(clips["blue"], 1.0))

    FfmpegCompositor(tmp_path).render_segment(clips["red"], segment, FRAMES, PROFILE, out, look)

    assert frame_count(out) == FRAMES
    assert frame_rgb(out, 5).mean(axis=0)[0] > 200  # still all the outgoing clip
    last = frame_rgb(out, FRAMES - 1).mean(axis=0)
    assert last[2] > last[0]  # the blend has reached the next clip


def test_beat_is_law_joined_transitions_keep_every_cut_on_its_frame(
    clips: dict[str, Path], tmp_path: Path
) -> None:
    compositor = FfmpegCompositor(tmp_path)
    lengths = (FRAMES, 23, 37)
    kinds = ("whip_left", "flash", "cut")
    names = ("red", "blue", "red")
    parts = []
    for index, (frames, kind) in enumerate(zip(lengths, kinds, strict=True)):
        part = tmp_path / f"p{index}.mp4"
        following = names[index + 1] if index < 2 else None
        next_clip = NextClip(clips[following], 1.0) if following else None
        compositor.render_segment(
            clips[names[index]],
            seg(transition_out=Transition(type=kind, duration=0.15)),
            frames,
            PROFILE,
            part,
            SegmentLook(next_clip=next_clip),
        )
        parts.append(part)
    joined = tmp_path / "joined.mp4"

    compositor.join(parts, joined)

    assert frame_count(joined) == sum(lengths)
    assert frame_rgb(joined, FRAMES).mean(axis=0)[2] > 200  # first frame after the cut is clean
    assert frame_rgb(joined, FRAMES + 23).mean(axis=0)[0] > 200


def test_a_source_that_runs_out_still_gives_every_frame(
    clips: dict[str, Path], tmp_path: Path
) -> None:
    out = tmp_path / "out.mp4"

    FfmpegCompositor(tmp_path).render_segment(clips["short"], seg(), 60, PROFILE, out)

    assert frame_count(out) == 60


def test_the_style_lut_changes_the_color_at_full_strength(
    clips: dict[str, Path], tmp_path: Path
) -> None:
    cube(tmp_path / "swap.cube", "swap")
    out = tmp_path / "out.mp4"
    look = SegmentLook(grade=Grade(lut="swap", intensity=1.0, grain=0.0))

    FfmpegCompositor(tmp_path).render_segment(clips["red"], seg(), FRAMES, PROFILE, out, look)

    red, _, blue = frame_rgb(out, 10).mean(axis=0)
    assert blue > 230
    assert red < 25
    assert frame_count(out) == FRAMES


def test_grade_intensity_blends_the_lut_over_the_original(
    clips: dict[str, Path], tmp_path: Path
) -> None:
    cube(tmp_path / "swap.cube", "swap")
    out = tmp_path / "out.mp4"
    look = SegmentLook(grade=Grade(lut="swap", intensity=0.25, grain=0.0))

    FfmpegCompositor(tmp_path).render_segment(clips["red"], seg(), FRAMES, PROFILE, out, look)

    red, _, blue = frame_rgb(out, 10).mean(axis=0)
    assert red == pytest.approx(255 * 0.75, abs=12)
    assert blue == pytest.approx(255 * 0.25, abs=12)


def test_rule_4_log_footage_gets_the_log_lut_before_the_style_grade(
    clips: dict[str, Path], tmp_path: Path
) -> None:
    cube(tmp_path / DJI_LOG_LUT, "half")
    cube(tmp_path / "swap.cube", "swap")
    out = tmp_path / "out.mp4"
    look = SegmentLook(grade=Grade(lut="swap", intensity=1.0, grain=0.0))

    FfmpegCompositor(tmp_path).render_segment(
        clips["red"], seg(source=LOG), FRAMES, PROFILE, out, look
    )

    red, _, blue = frame_rgb(out, 10).mean(axis=0)
    assert blue == pytest.approx(127, abs=15)  # halved, then swapped
    assert red < 25


def test_a_missing_lut_renders_ungraded_rather_than_failing(
    clips: dict[str, Path], tmp_path: Path
) -> None:
    out = tmp_path / "out.mp4"
    look = SegmentLook(grade=Grade(lut="nothing", intensity=1.0, grain=0.0))

    FfmpegCompositor(tmp_path).render_segment(clips["red"], seg(), FRAMES, PROFILE, out, look)

    assert frame_rgb(out, 10).mean(axis=0)[0] > 200


def test_grain_adds_noise_and_changes_every_frame(clips: dict[str, Path], tmp_path: Path) -> None:
    clean = tmp_path / "clean.mp4"
    grainy = tmp_path / "grainy.mp4"
    compositor = FfmpegCompositor(tmp_path)
    compositor.render_segment(clips["blue"], seg(), FRAMES, PROFILE, clean)
    grade = Grade(lut="nothing", intensity=1.0, grain=0.5)

    compositor.render_segment(
        clips["blue"], seg(), FRAMES, PROFILE, grainy, SegmentLook(grade=grade)
    )

    assert frame_rgb(grainy, 10).std() > frame_rgb(clean, 10).std() + 1
    assert frame_count(grainy) == FRAMES


def test_b5_motion_blur_keeps_the_frame_count_and_smears_only_while_moving(
    tmp_path: Path,
) -> None:
    moving = tmp_path / "moving.mp4"
    ffmpeg(
        "-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=3",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", moving,
    )  # fmt: skip
    sharp = tmp_path / "sharp.mp4"
    blurred = tmp_path / "blurred.mp4"
    compositor = FfmpegCompositor(tmp_path)
    zoom = Effect(type="zoomPunch", at=0.0, duration=0.5, strength=0.3)
    segment = seg(effects=(zoom,))

    compositor.render_segment(moving, segment, FRAMES, PROFILE, sharp)
    compositor.render_segment(
        moving, segment, FRAMES, PROFILE, blurred, SegmentLook(motion_blur=0.63)
    )

    assert frame_count(blurred) == FRAMES
    assert np.abs(frame_rgb(blurred, 8) - frame_rgb(sharp, 8)).mean() > 1.5
    assert np.abs(frame_rgb(blurred, 25) - frame_rgb(sharp, 25)).mean() < 1.5


def tone(target: Path, frequency: int, seconds: float, volume: float) -> Path:
    ffmpeg(
        "-f", "lavfi", "-i", f"sine=frequency={frequency}:sample_rate=48000:duration={seconds}",
        "-af", f"volume={volume}", "-ac", "2", target,
    )  # fmt: skip
    return target


def decoded(path: Path) -> Audio:
    output = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path),
            "-map", "0:a:0", "-f", "f32le", "-ac", "2", "-ar", str(SAMPLE_RATE), "-",
        ],
        capture_output=True, check=True,
    )  # fmt: skip
    return np.frombuffer(output.stdout, dtype=np.float32).reshape(-1, 2).copy()


def rms_db(samples: Audio) -> float:
    return float(20 * np.log10(np.sqrt(np.mean(samples**2))))


def band_amplitude(samples: Audio, frequency: int) -> float:
    """Amplitude of one sine in the left channel."""
    mono = samples[:, 0] * np.hanning(len(samples))
    spectrum = np.abs(np.fft.rfft(mono)) / (np.sum(np.hanning(len(samples))) / 2)
    bins = np.fft.rfftfreq(len(samples), 1 / SAMPLE_RATE)
    near = np.abs(bins - frequency) < 15
    return float(spectrum[near].max())


def lufs(samples: Audio) -> float:
    return float(pyloudnorm.Meter(SAMPLE_RATE).integrated_loudness(samples))


@pytest.fixture(scope="module")
def sound(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    folder = tmp_path_factory.mktemp("sound")
    sfx = folder / "sfx"
    sfx.mkdir()
    silent_video = folder / "video.mp4"
    ffmpeg(
        "-f", "lavfi", "-i", "color=c=black:s=160x90:r=30:d=6",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", silent_video,
    )  # fmt: skip
    tone(sfx / "whoosh.wav", 5000, 0.5, 1.0)
    return {
        "sfx": sfx,
        "video": silent_video,
        "music": tone(folder / "music.wav", 200, 8.0, 0.1),
        "speech": tone(folder / "speech.wav", 1000, 4.0, 0.0001),
    }


def test_b8_music_alone_stays_at_minus_14_lufs_stereo(
    sound: dict[str, Path], tmp_path: Path
) -> None:
    out = tmp_path / "out.mp4"

    FfmpegAudioFinisher(sound["sfx"]).add_music(sound["video"], sound["music"], 1.0, 6.0, out)

    assert lufs(decoded(out)) == pytest.approx(-14.0, abs=0.3)


def test_b8_sfx_land_at_their_time_18_db_down_and_the_mix_stays_at_minus_14_lufs(
    sound: dict[str, Path], tmp_path: Path
) -> None:
    alone = tmp_path / "alone.mp4"
    mixed = tmp_path / "mixed.mp4"
    finisher = FfmpegAudioFinisher(sound["sfx"])
    cues = tuple(SfxPlacement("whoosh", at, -18.0) for at in (1.0, 3.0))

    finisher.add_music(sound["video"], sound["music"], 1.0, 6.0, alone)
    finisher.add_music(sound["video"], sound["music"], 1.0, 6.0, mixed, AudioMix(sfx=cues))

    samples = decoded(mixed)
    assert samples.shape[0] == pytest.approx(6 * SAMPLE_RATE, abs=SAMPLE_RATE * 0.05)
    assert lufs(samples) == pytest.approx(-14.0, abs=0.3)
    window = samples[int(1.1 * SAMPLE_RATE) : int(1.4 * SAMPLE_RATE)]
    gap = samples[int(1.6 * SAMPLE_RATE) : int(2.9 * SAMPLE_RATE)]
    trim = band_amplitude(gap, 200) / band_amplitude(decoded(alone)[SAMPLE_RATE:], 200)
    expected = 20 * np.log10(10 ** (-18 / 20) * trim)
    assert 20 * np.log10(band_amplitude(window, 5000)) == pytest.approx(expected, abs=0.7)
    assert band_amplitude(gap, 5000) < 0.002


def test_b8_music_ducks_8_db_under_kept_clip_audio(sound: dict[str, Path], tmp_path: Path) -> None:
    out = tmp_path / "out.mp4"
    kept = KeptClipAudio(sound["speech"], 0.0, 2.0, 2.0)

    FfmpegAudioFinisher(sound["sfx"]).add_music(
        sound["video"], sound["music"], 1.0, 6.0, out, AudioMix(speech=(kept,))
    )

    samples = decoded(out)
    ducked = samples[int(2.3 * SAMPLE_RATE) : int(3.7 * SAMPLE_RATE)]
    open_music = samples[int(0.3 * SAMPLE_RATE) : int(1.7 * SAMPLE_RATE)]
    assert rms_db(open_music) - rms_db(ducked) == pytest.approx(8.0, abs=0.3)
    assert lufs(samples) == pytest.approx(-14.0, abs=0.3)


def test_b8_a_missing_sfx_file_is_skipped(sound: dict[str, Path], tmp_path: Path) -> None:
    out = tmp_path / "out.mp4"
    mix = AudioMix(sfx=(SfxPlacement("nothing", 1.0, -18.0),))

    FfmpegAudioFinisher(sound["sfx"]).add_music(sound["video"], sound["music"], 1.0, 6.0, out, mix)

    assert lufs(decoded(out)) == pytest.approx(-14.0, abs=0.3)
