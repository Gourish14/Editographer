"""The one place that runs FFmpeg tools. Spec: specs/11-coding-standards.md#4-worker--python-312"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence

import structlog

log = structlog.get_logger()
STDERR_TAIL_CHARS = 500


class FfmpegError(Exception):
    """A tool exited with an error. Holds the end of its stderr."""


def run_tool(arguments: Sequence[str]) -> str:
    """Runs a tool from an argument list, never a shell string, and returns its stdout."""
    return run_tool_for_bytes(arguments).decode("utf-8", errors="replace")


def run_tool_for_bytes(arguments: Sequence[str]) -> bytes:
    """Like run_tool, for tools that write binary data to stdout."""
    log.info("ffmpeg.run", command=" ".join(arguments))
    try:
        result = subprocess.run(list(arguments), capture_output=True, check=False)
    except OSError as error:
        raise FfmpegError(f"Could not start {arguments[0]}: {error}") from error
    if result.returncode != 0:
        raise FfmpegError(result.stderr.decode("utf-8", errors="replace")[-STDERR_TAIL_CHARS:])
    return result.stdout
