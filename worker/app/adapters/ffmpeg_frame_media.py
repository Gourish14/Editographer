"""Frames in and out of video with FFmpeg. Spec: specs/04-pipeline.md#stages (6, 7)

Extraction feeds RIFE slow motion. Upscaling streams raw frames through the Real-ESRGAN session,
so a whole edit is never held as files: FFmpeg decodes, the model upscales, FFmpeg encodes.
"""

from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path
from typing import IO

import numpy as np
import structlog

from app.adapters.ffmpeg_runner import FfmpegError, run_tool
from app.domain.errors import ErrorCode, RenderError
from app.ports.enhance import Frame, FrameSize, Upscaler
from app.ports.frames import UpscaleSpec

log = structlog.get_logger()

BASE_ARGUMENTS = ("ffmpeg", "-hide_banner", "-loglevel", "error", "-y")
PIXEL_FORMAT = "rgb48le"
BYTES_PER_PIXEL = 6
"""16-bit RGB keeps the 10-bit precision of the joined edit through the upscaler."""
STDERR_TAIL_CHARS = 500


class FfmpegFrameMedia:
    def extract_frames(
        self,
        source: Path,
        start: float,
        duration: float,
        fps: float,
        folder: Path,
        width: int | None = None,
    ) -> int:
        folder.mkdir(parents=True, exist_ok=True)
        video_filter = f"fps={fps}" if width is None else f"fps={fps},scale={width}:-2"
        try:
            run_tool(
                [
                    *BASE_ARGUMENTS,
                    "-ss",
                    f"{start:.4f}",
                    "-t",
                    f"{duration:.4f}",
                    "-i",
                    str(source),
                    "-vf",
                    video_filter,
                    "-start_number",
                    "1",
                    str(folder / "%06d.png"),
                ]
            )
        except FfmpegError as error:
            raise RenderError(str(error), ErrorCode.RENDER_FAILED) from error
        return len(list(folder.glob("*.png")))


class FfmpegVideoUpscaler:
    def __init__(self, upscaler: Upscaler) -> None:
        self._upscaler = upscaler

    def upscale_video(self, spec: UpscaleSpec, on_frame: Callable[[int], None]) -> None:
        with ExitStack() as stack:
            errors = stack.enter_context(tempfile.TemporaryFile())
            decoder = stack.enter_context(
                subprocess.Popen(_decode(spec), stdout=subprocess.PIPE, stderr=errors)
            )
            encoder = stack.enter_context(
                subprocess.Popen(_encode(spec), stdin=subprocess.PIPE, stderr=errors)
            )
            stack.callback(_stop, decoder, encoder)
            session = stack.enter_context(self._upscaler.session(spec.cool_mode))
            assert decoder.stdout is not None
            assert encoder.stdin is not None
            for done in range(1, spec.frames + 1):
                frame = _read(decoder.stdout, spec.source_size)
                if frame is None:
                    raise RenderError(f"The video ended after {done - 1} of {spec.frames} frames")
                encoder.stdin.write(session.upscale(frame, spec.size).tobytes())
                on_frame(done)
            encoder.stdin.close()
            if encoder.wait() != 0:
                raise RenderError(_tail(errors), ErrorCode.RENDER_FAILED)
        log.info("render.upscaled", frames=spec.frames, width=spec.size.width)


def _decode(spec: UpscaleSpec) -> list[str]:
    return [
        *BASE_ARGUMENTS,
        "-i",
        str(spec.source),
        "-f",
        "rawvideo",
        "-pix_fmt",
        PIXEL_FORMAT,
        "-frames:v",
        str(spec.frames),
        "-",
    ]


def _encode(spec: UpscaleSpec) -> list[str]:
    return [
        *BASE_ARGUMENTS,
        "-f",
        "rawvideo",
        "-pix_fmt",
        PIXEL_FORMAT,
        "-s",
        f"{spec.size.width}x{spec.size.height}",
        "-r",
        str(spec.fps),
        "-i",
        "-",
        "-frames:v",
        str(spec.frames),
        "-c:v",
        "hevc_nvenc",
        "-preset",
        spec.preset,
        "-rc",
        "vbr",
        "-cq",
        str(spec.quality),
        "-b:v",
        "0",
        "-profile:v",
        "main10",
        "-pix_fmt",
        "p010le",
        str(spec.target),
    ]


def _read(stream: IO[bytes], size: FrameSize) -> Frame | None:
    wanted = size.width * size.height * BYTES_PER_PIXEL
    data = stream.read(wanted)
    if len(data) < wanted:
        return None
    return np.frombuffer(data, np.uint16).reshape(size.height, size.width, 3).copy()


def _stop(*processes: subprocess.Popen[bytes]) -> None:
    for process in processes:
        if process.poll() is None:
            process.kill()


def _tail(errors: IO[bytes]) -> str:
    errors.seek(0)
    return errors.read().decode("utf-8", errors="replace")[-STDERR_TAIL_CHARS:]
