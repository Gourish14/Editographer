"""Shot captions and text behind the subject.

Spec: specs/05-editing-brain.md B2, B8, B10; specs/04-pipeline.md stages 3 and 6 [T-408]
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TypeVar

import cv2
import httpx
import numpy as np

from app.adapters.ffmpeg_text_overlay import overlay_chain
from app.adapters.ollama_captioner import OllamaCaptioner
from app.application.analyze_shots import MAX_CAPTIONED, AnalyzeShots
from app.application.subject_matte import SubjectMatte
from app.domain.brain.director import director_brief
from app.domain.brain.planner import ClipInput, build_edit_plan
from app.domain.brain.text_rules import TextItem
from app.domain.constraints import Constraints, Direction, DirectorDecision
from app.domain.photo import FocusBox, FocusSource
from app.domain.shots import FrameSample, SubjectSample
from tests.unit.shot_fakes import FakeEncoder, FakeObjects
from tests.unit.test_analyze_shots import Frames, Scenes
from tests.unit.test_planner import SETTINGS, analysis, clips, measure, music_map

T = TypeVar("T")


class FakeGpu:
    def status(self) -> None:
        return None

    @contextmanager
    def loaded(self, load: Callable[[], T]) -> Iterator[T]:
        yield load()


class Captions:
    def __init__(self, fail: bool = False) -> None:
        self.asked: list[float] = []
        self.fail = fail

    def caption_frames(self, path: Path, times: Sequence[float]) -> tuple[str, ...]:
        self.asked = list(times)
        return tuple("" if self.fail else f"caption {i}" for i, _ in enumerate(times))


class DenseFrames:
    def sample(self, path: Path) -> tuple[FrameSample, ...]:
        return tuple(FrameSample(i * 0.1, 1.0, 0.5, 100.0, 0.5, 0.0) for i in range(90))


def test_b2_only_the_best_40_shots_of_a_clip_are_captioned() -> None:
    spans = tuple((i * 0.2, i * 0.2 + 0.2) for i in range(45))
    captions = Captions()
    shots = AnalyzeShots(Scenes(spans), DenseFrames(), FakeObjects(), FakeEncoder(), captions)

    measures = shots.run(Path("p.mp4"), 9.0)

    assert len(captions.asked) == MAX_CAPTIONED
    assert sum(1 for m in measures if m.caption) == MAX_CAPTIONED


def test_b2_a_caption_failure_means_no_caption_not_a_failed_job() -> None:
    shots = AnalyzeShots(Scenes(()), Frames(), FakeObjects(), FakeEncoder(), Captions(fail=True))

    assert shots.run(Path("p.mp4"), 5.0)[0].caption == ""


def test_b2_ollama_captioner_gives_empty_captions_when_ollama_is_down(tmp_path: Path) -> None:
    clip = tmp_path / "c.mp4"
    writer = cv2.VideoWriter(str(clip), cv2.VideoWriter.fourcc(*"mp4v"), 10, (64, 64))
    for _ in range(20):
        writer.write(np.zeros((64, 64, 3), np.uint8))
    writer.release()

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    client = httpx.Client(base_url="http://x", transport=httpx.MockTransport(refuse))

    assert OllamaCaptioner(client, FakeGpu()).caption_frames(clip, (0.1, 0.5)) == ("", "")


def test_b2_ollama_captioner_sends_keep_alive_zero_on_the_last_call(tmp_path: Path) -> None:
    clip = tmp_path / "c.mp4"
    writer = cv2.VideoWriter(str(clip), cv2.VideoWriter.fourcc(*"mp4v"), 10, (64, 64))
    for _ in range(20):
        writer.write(np.zeros((64, 64, 3), np.uint8))
    writer.release()
    sent: list[Any] = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": " A  dog runs. "}})

    client = httpx.Client(base_url="http://x", transport=httpx.MockTransport(answer))

    result = OllamaCaptioner(client, FakeGpu()).caption_frames(clip, (0.1, 0.5))

    assert result == ("A dog runs.", "A dog runs.")
    assert [body["keep_alive"] for body in sent] == ["1m", 0]
    assert sent[0]["model"] == "qwen2.5vl:3b"


def test_b10_the_director_sees_each_shots_caption() -> None:
    captioned = analysis(measure(0.0, 10.0).model_copy(update={"caption": "a dog on a beach"}))

    brief = json.loads(director_brief(music_map(), [ClipInput("v0", captioned)], SETTINGS))

    assert brief["shots"][0]["caption"] == "a dog on a beach"
    assert "caption" not in json.loads(director_brief(music_map(), clips(), SETTINGS))["shots"][0]


def _subject_plan(with_subject: bool) -> Any:
    shot = measure(0.0, 10.0)
    if with_subject:
        shot = shot.model_copy(update={"subject_track": (SubjectSample(time=1.0, x=0.5, y=0.5),)})
    direction = Direction(DirectorDecision(constraints=Constraints(text=("HELLO",))))
    return build_edit_plan(
        "m1", music_map(), [ClipInput("v0", analysis(shot))], SETTINGS, direction
    )


def test_b8_prompt_text_goes_behind_the_subject_when_the_shot_has_one() -> None:
    assert [item.behind_subject for item in _subject_plan(True).text] == [True]


def test_b8_text_stays_in_front_when_the_shot_has_no_subject() -> None:
    assert [item.behind_subject for item in _subject_plan(False).text] == [False]


ITEM = TextItem("HI", 1.0, 2.0, "pop_on_beat", True)


def test_b8_a_matte_puts_the_subject_back_over_the_text_with_exact_frames() -> None:
    graph = overlay_chain("0:v", [ITEM], 1, mattes={0: 2}, fps=30)

    assert "alphamerge" in graph
    assert "trim=start_frame=30:end_frame=90" in graph
    assert "[2:v]format=gray,trim=end_frame=60" in graph
    assert "yuva420p10le" in graph


def test_b8_no_matte_keeps_the_plain_overlay() -> None:
    assert "alphamerge" not in overlay_chain("0:v", [ITEM], 1)


class Media:
    def __init__(self, frames: int) -> None:
        self.frames = frames

    def extract_frames(
        self, source: Path, start: float, duration: float, fps: float, folder: Path
    ) -> int:
        folder.mkdir(parents=True)
        for number in range(1, self.frames + 1):
            (folder / f"{number:06d}.png").write_bytes(b"x")
        return self.frames


class Locator:
    def __init__(self, source: FocusSource) -> None:
        self.source = source

    def locate(self, image: Path) -> FocusBox:
        return FocusBox(0.4, 0.2, 0.2, 0.1, self.source)


class Masks:
    def __init__(self, count: int) -> None:
        self.count = count
        self.points: Sequence[tuple[float, float]] = ()

    def track(
        self, frames: Sequence[Path], points: Sequence[tuple[float, float]], folder: Path
    ) -> tuple[Path, ...]:
        self.points = points
        folder.mkdir(parents=True)
        paths = [folder / f"{n:06d}.png" for n in range(1, self.count + 1)]
        for path in paths:
            path.write_bytes(b"m")
        return tuple(paths)


def test_b8_matte_has_exactly_one_mask_per_frame_of_the_window(tmp_path: Path) -> None:
    masks = Masks(55)
    matte = SubjectMatte(Media(60), Locator(FocusSource.FACE), masks)

    folder = matte.make(Path("v.mp4"), ITEM, 30, tmp_path)

    assert folder is not None
    assert len(list(folder.glob("*.png"))) == 60
    assert masks.points[0] == (0.5, 0.25) and masks.points[1][1] > masks.points[0][1]


def test_b8_no_face_means_no_matte_and_the_text_stays_in_front(tmp_path: Path) -> None:
    matte = SubjectMatte(Media(60), Locator(FocusSource.SALIENCY), Masks(60))

    assert matte.make(Path("v.mp4"), ITEM, 30, tmp_path) is None


def test_b8_no_mask_from_sam_means_no_matte(tmp_path: Path) -> None:
    matte = SubjectMatte(Media(60), Locator(FocusSource.FACE), Masks(0))

    assert matte.make(Path("v.mp4"), ITEM, 30, tmp_path) is None
