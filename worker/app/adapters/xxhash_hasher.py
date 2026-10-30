"""Content hash. Spec: specs/04-pipeline.md#stages (1)"""

from __future__ import annotations

from pathlib import Path

import xxhash

SAMPLE_BYTES = 16 * 1024 * 1024


class XxhashHasher:
    """Reads only the ends of the file, so a 16 GB .OSV hashes in moments."""

    def hash_file(self, path: Path) -> str:
        size = path.stat().st_size
        digest = xxhash.xxh3_128()
        digest.update(str(size).encode())
        with path.open("rb") as file:
            digest.update(file.read(SAMPLE_BYTES))
            if size > SAMPLE_BYTES:
                file.seek(max(SAMPLE_BYTES, size - SAMPLE_BYTES))
                digest.update(file.read(SAMPLE_BYTES))
        return digest.hexdigest()
