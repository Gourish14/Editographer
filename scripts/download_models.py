"""Download model weights into models/ with SHA-256 checks. Spec: specs/09-local-setup.md#setupbat-run-once

Standard library only, so it runs before the worker's environment exists. Safe to re-run:
verified files are skipped and interrupted downloads resume from their .part file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = Path(__file__).resolve().parent / "models.json"
CHUNK_BYTES = 1024 * 1024
MAX_ATTEMPTS = 8
RETRY_WAIT_SEC = 3.0
REQUEST_TIMEOUT_SEC = 60.0
HTTP_PARTIAL_CONTENT = 206
HTTP_RANGE_NOT_SATISFIABLE = 416


class DownloadError(Exception):
    """A model could not be fetched or failed its checksum."""


@dataclass(frozen=True)
class ModelSpec:
    name: str
    phase: int
    url: str
    path: str
    size: int
    sha256: str


def load_manifest(path: Path) -> list[ModelSpec]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [ModelSpec(**entry) for entry in data["models"]]


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _fetch_into(spec: ModelSpec, part: Path) -> None:
    """Append the remaining bytes of the model to part, resuming when the server allows it."""
    offset = part.stat().st_size if part.exists() else 0
    request = urllib.request.Request(spec.url)
    if offset:
        request.add_header("Range", f"bytes={offset}-")
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SEC) as response:
            # A server that ignores Range sends the whole file, so start over.
            mode = "ab" if response.status == HTTP_PARTIAL_CONTENT else "wb"
            with part.open(mode) as output:
                while chunk := response.read(CHUNK_BYTES):
                    output.write(chunk)
    except urllib.error.HTTPError as error:
        if error.code != HTTP_RANGE_NOT_SATISFIABLE:
            raise


def download(spec: ModelSpec, models_dir: Path, wait_sec: float = RETRY_WAIT_SEC) -> str:
    """Make sure one verified model file is in place. Returns "present" or "downloaded"."""
    target = models_dir / spec.path
    if target.exists() and sha256_of(target) == spec.sha256:
        return "present"

    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            _fetch_into(spec, part)
        except (OSError, urllib.error.URLError) as error:
            print(f"  {spec.name}: attempt {attempt}/{MAX_ATTEMPTS} stopped ({error})")
        if part.exists() and part.stat().st_size >= spec.size:
            break
        time.sleep(wait_sec)

    if not part.exists() or part.stat().st_size < spec.size:
        raise DownloadError(f"{spec.name}: incomplete after {MAX_ATTEMPTS} attempts")
    actual = sha256_of(part)
    if actual != spec.sha256:
        part.unlink()
        raise DownloadError(f"{spec.name}: checksum mismatch, got {actual}")
    part.replace(target)
    return "downloaded"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download model weights into models/.")
    parser.add_argument("--phase", type=int, default=1, help="highest roadmap phase to fetch")
    parser.add_argument("--models-dir", type=Path, default=ROOT / "models")
    args = parser.parse_args(argv)

    specs = [spec for spec in load_manifest(MANIFEST) if spec.phase <= args.phase]
    try:
        for spec in specs:
            print(f"{spec.name}: {download(spec, args.models_dir)}")
    except DownloadError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
