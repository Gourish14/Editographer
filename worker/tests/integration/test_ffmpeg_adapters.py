"""FFmpeg adapters on real generated media. Spec: specs/04-pipeline.md#stages (1) [T-109]"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from app.adapters.ffmpeg_media_tools import FfmpegMediaTools
from app.adapters.ffmpeg_probe import FfmpegProbe, parse_probe_output
from app.adapters.file_cache import FileCache
from app.adapters.xxhash_hasher import SAMPLE_BYTES, XxhashHasher
from app.domain.analysis import StoredAnalysis
from app.domain.errors import AnalysisError, ErrorCode

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs FFmpeg on PATH")


def generate(target: Path, *arguments: str) -> Path:
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *arguments, str(target)],
        check=True,
    )
    return target


@pytest.fixture
def clip(tmp_path: Path) -> Path:
    return generate(
        tmp_path / "clip.mp4",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=1280x720:rate=30:duration=2",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=2",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
    )


@needs_ffmpeg
def test_probe_reads_a_real_video(clip: Path) -> None:
    info = FfmpegProbe().probe(clip)

    assert info.codec == "h264"
    assert (info.width, info.height) == (1280, 720)
    assert info.fps == pytest.approx(30.0)
    assert info.duration_sec == pytest.approx(2.0, abs=0.1)
    assert info.bit_depth == 8


@needs_ffmpeg
def test_probe_reads_real_audio(tmp_path: Path) -> None:
    song = generate(tmp_path / "song.wav", "-f", "lavfi", "-i", "sine=frequency=220:duration=1")

    info = FfmpegProbe().probe(song)

    assert info.width is None
    assert info.fps is None
    assert info.duration_sec == pytest.approx(1.0, abs=0.05)


@needs_ffmpeg
def test_a_file_that_is_not_media_is_unsupported(tmp_path: Path) -> None:
    junk = tmp_path / "junk.mp4"
    junk.write_text("not a video")

    with pytest.raises(AnalysisError) as failure:
        FfmpegProbe().probe(junk)

    assert failure.value.code is ErrorCode.ASSET_UNSUPPORTED


def test_a_quarter_turn_swaps_width_and_height() -> None:
    info = parse_probe_output(
        {
            "streams": [
                {
                    "codec_type": "video",
                    "width": 1920,
                    "height": 1080,
                    "avg_frame_rate": "30000/1001",
                    "side_data_list": [{"rotation": -90}],
                    "pix_fmt": "yuv420p10le",
                }
            ],
            "format": {"duration": "4.5", "tags": {"encoder": "DJI"}},
        }
    )

    assert (info.width, info.height) == (1080, 1920)
    assert info.rotation == 270
    assert info.fps == pytest.approx(29.97)
    assert info.bit_depth == 10
    assert info.tags == ("encoder=DJI",)


def test_an_older_rotate_tag_is_understood() -> None:
    info = parse_probe_output(
        {
            "streams": [
                {
                    "codec_type": "video",
                    "width": 100,
                    "height": 50,
                    "r_frame_rate": "25/1",
                    "avg_frame_rate": "0/0",
                    "tags": {"rotate": "180"},
                }
            ]
        }
    )

    assert (info.width, info.height) == (100, 50)
    assert info.rotation == 180
    assert info.fps == 25.0
    assert info.duration_sec is None


@needs_ffmpeg
@pytest.mark.gpu
def test_proxy_is_720p_h264_with_no_audio(tmp_path: Path) -> None:
    source = generate(
        tmp_path / "big.mp4",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=1920x1080:rate=30:duration=1",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
    )
    target = tmp_path / "proxies" / "a.mp4"

    FfmpegMediaTools().make_proxy(source, target)

    info = FfmpegProbe().probe(target)
    assert info.codec == "h264"
    assert info.height == 720
    assert info.width == 1280
    assert not any(tag.startswith("handler_name=SoundHandler") for tag in info.tags)


@needs_ffmpeg
def test_thumbnail_is_a_small_jpeg(clip: Path, tmp_path: Path) -> None:
    target = tmp_path / "cache" / "thumbnail.jpg"

    FfmpegMediaTools().make_thumbnail(clip, target, 0.2)

    info = FfmpegProbe().probe(target)
    assert info.codec == "mjpeg"
    assert info.height == 360


def test_adopting_a_proxy_copies_the_file(tmp_path: Path) -> None:
    source = tmp_path / "a.lrf"
    source.write_text("lrf")

    FfmpegMediaTools().adopt_proxy(source, tmp_path / "proxies" / "a.mp4")

    assert (tmp_path / "proxies" / "a.mp4").read_text() == "lrf"
    assert source.exists()


def test_hash_depends_on_content_and_size(tmp_path: Path) -> None:
    hasher = XxhashHasher()
    first = tmp_path / "a"
    same = tmp_path / "b"
    other = tmp_path / "c"
    first.write_bytes(b"x" * 100)
    same.write_bytes(b"x" * 100)
    other.write_bytes(b"y" * 100)

    assert hasher.hash_file(first) == hasher.hash_file(same)
    assert hasher.hash_file(first) != hasher.hash_file(other)


def test_hash_sees_the_end_of_a_large_file(tmp_path: Path) -> None:
    hasher = XxhashHasher()
    start = b"s" * SAMPLE_BYTES
    first = tmp_path / "a"
    second = tmp_path / "b"
    first.write_bytes(start + b"middle" + b"end-1")
    second.write_bytes(start + b"middle" + b"end-2")

    assert hasher.hash_file(first) != hasher.hash_file(second)


def analysis(file_hash: str = "h") -> StoredAnalysis:
    return StoredAnalysis(
        file_hash=file_hash,
        codec="h264",
        width=1,
        height=1,
        fps=30.0,
        rotation=0,
        duration_sec=1.0,
        transfer=None,
        bit_depth=8,
        camera_mode="FLAT",
        log_profile=None,
        native_slow_mo=False,
    )


def test_cache_round_trip(tmp_path: Path) -> None:
    cache = FileCache(tmp_path)

    cache.save(analysis())

    assert cache.load("h") == analysis()
    assert cache.analysis_path("h") == "cache/h/analysis.json"
    assert cache.thumbnail_file("h") == tmp_path / "cache" / "h" / "thumbnail.jpg"


def test_cache_misses_for_unknown_or_damaged_documents(tmp_path: Path) -> None:
    cache = FileCache(tmp_path)
    cache.save(analysis())
    (tmp_path / "cache" / "h" / "analysis.json").write_text("{broken")

    assert cache.load("h") is None
    assert cache.load("unknown") is None


def test_cache_misses_for_an_outdated_version(tmp_path: Path) -> None:
    cache = FileCache(tmp_path)
    cache.save(analysis().model_copy(update={"version": 0}))

    assert cache.load("h") is None
