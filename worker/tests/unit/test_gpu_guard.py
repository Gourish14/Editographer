"""Tests for the GPU guard. Spec: specs/09-local-setup.md#6-gb-vram-model-profile [T-108]"""

from __future__ import annotations

import threading

import pytest

from app.adapters.nvml_gpu_guard import NvmlGpuGuard

WAIT_SEC = 5.0


def test_the_model_is_loaded_used_and_the_cache_emptied_after() -> None:
    calls: list[str] = []
    guard = NvmlGpuGuard(empty_cache=lambda: calls.append("empty"))

    with guard.loaded(lambda: "model") as model:
        calls.append(model)

    assert calls == ["model", "empty"]


def test_vram_is_freed_even_when_the_work_fails() -> None:
    calls: list[str] = []
    guard = NvmlGpuGuard(empty_cache=lambda: calls.append("empty"))

    with pytest.raises(ValueError, match="boom"), guard.loaded(lambda: "model"):
        raise ValueError("boom")

    assert calls == ["empty"]


def test_vram_is_freed_when_loading_fails() -> None:
    calls: list[str] = []
    guard = NvmlGpuGuard(empty_cache=lambda: calls.append("empty"))

    def load() -> str:
        raise MemoryError

    with pytest.raises(MemoryError), guard.loaded(load):
        pass

    assert calls == ["empty"]


def test_only_one_model_is_on_the_gpu_at_a_time() -> None:
    guard = NvmlGpuGuard(empty_cache=lambda: None)
    first_loaded = threading.Event()
    release_first = threading.Event()
    second_loaded = threading.Event()

    def first() -> None:
        with guard.loaded(lambda: "a"):
            first_loaded.set()
            release_first.wait(WAIT_SEC)

    def second() -> None:
        with guard.loaded(lambda: "b"):
            second_loaded.set()

    threads = [threading.Thread(target=first), threading.Thread(target=second)]
    threads[0].start()
    first_loaded.wait(WAIT_SEC)
    threads[1].start()

    assert not second_loaded.wait(0.2)
    release_first.set()
    for thread in threads:
        thread.join(WAIT_SEC)
    assert second_loaded.is_set()
