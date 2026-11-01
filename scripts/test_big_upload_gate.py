"""Tests for the big upload gate script. Spec: specs/02-architecture.md#communication [T-418]

Run with: python -m unittest discover -s scripts -p "test_*.py"
"""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

import big_upload_gate as gate

SIZE = 5 * 1024 * 1024 + 123
CHUNK = 1024 * 1024


class InputFile(unittest.TestCase):
    def test_the_input_has_exactly_the_size_and_the_reported_sha(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "input.osv"
            sha = gate.write_input(path, SIZE, block=1000003)
            assert path.stat().st_size == SIZE
            assert gate.sha256_file(path) == sha

    def test_the_input_is_not_all_zeros_and_repeats_for_a_seed(self) -> None:
        first = b"".join(gate.make_blocks(SIZE, block=1000003))
        again = b"".join(gate.make_blocks(SIZE, block=1000003))
        assert first == again and any(first[:4096]) and any(first[-4096:])
        assert hashlib.sha256(first).hexdigest() == hashlib.sha256(again).hexdigest()

    def test_sixteen_gib_is_beyond_every_32_bit_limit(self) -> None:
        assert 16 * gate.GIB > 2**33

    def test_the_chunk_size_is_the_frontends(self) -> None:
        source = (
            gate.ROOT / "frontend/src/app/core/services/upload.service.ts"
        ).read_text()
        assert (
            f"CHUNK_BYTES = {gate.CHUNK_BYTES // 1024 // 1024} * 1024 * 1024" in source
        )


class Verdict(unittest.TestCase):
    SHA = "a" * 64

    def judged(self, sent: int, sha: str | None = SHA, stored: int | None = SIZE):
        return gate.judge(SIZE, CHUNK, sent, stored, sha, self.SHA)

    def test_sending_exactly_the_size_passes(self) -> None:
        assert self.judged(SIZE) == []

    def test_resending_one_chunk_still_passes(self) -> None:
        assert self.judged(SIZE + CHUNK) == []

    def test_resending_more_than_one_chunk_fails(self) -> None:
        assert any("twice" in f for f in self.judged(SIZE + CHUNK + 1))

    def test_a_wrong_hash_or_size_fails(self) -> None:
        assert any("SHA" in f for f in self.judged(SIZE, sha="b" * 64))
        assert any("size" in f for f in self.judged(SIZE, stored=SIZE - 1))
        assert any("size" in f for f in self.judged(SIZE, stored=None))

    def test_sending_less_than_the_file_fails(self) -> None:
        assert any("less" in f for f in self.judged(SIZE - 1))

    def test_resent_bytes_never_go_negative(self) -> None:
        assert gate.resent_bytes(5, 10) == 0 and gate.resent_bytes(12, 10) == 2


class Parsing(unittest.TestCase):
    def test_heap_used_is_read_from_jcmd(self) -> None:
        text = " garbage-first heap   total reserved 262144K, committed 65536K, used 20480K [..]"
        assert gate.parse_heap_used_mb(text) == 20.0
        assert gate.parse_heap_used_mb("nothing") is None


if __name__ == "__main__":
    unittest.main()
