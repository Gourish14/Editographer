"""The real YOLO and OpenCLIP adapters on clips made from a real photo. [T-201]

Spec: specs/05-editing-brain.md#b2-shot-scoring-scoringpy, specs/09-local-setup.md

tests/fixtures/astronaut.jpg is NASA's portrait of Eileen Collins (public domain), as shipped in
scikit-image. It is the only test media with a real person and a real face.
"""

from __future__ import annotations

import gc
import shutil
import subprocess
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import TypeVar

import pytest
import torch

from app.adapters.clip_encoder import OpenClipEncoder
from app.adapters.nvml_gpu_guard import NvmlGpuGuard
from app.adapters.opencv_frame_sampler import OpenCvFrameSampler
from app.adapters.scenedetect_shots import SceneDetectShots
from app.adapters.yolo_detector import YoloObjectDetector
from app.application.analyze_shots import AnalyzeShots
from app.application.search_shots import SearchShots
from app.domain.brain.scoring import DUPLICATE_SIMILARITY, score_shots
from app.domain.brain.shot_tags import tag_phrase
from app.domain.errors import AnalysisError
from app.domain.shots import MotionDirection, ShotMeasure, cosine_similarity
from app.ports.gpu_guard import GpuGuard
from app.ports.shots import ObjectDetector, ShotEncoder

T = TypeVar("T")
MODELS = Path(__file__).resolve().parents[3] / "models"
YOLO_WEIGHTS = MODELS / "yolo" / "yolo11n.pt"
CLIP_WEIGHTS = MODELS / "clip" / "vit_b_32_openai.safetensors"
AESTHETIC_WEIGHTS = MODELS / "clip" / "sa_0_4_vit_b_32_linear.pth"
FACE_MODEL = MODELS / "mediapipe" / "blaze_face_short_range.tflite"
PHOTO = Path(__file__).resolve().parents[1] / "fixtures" / "astronaut.jpg"
HEAD_AND_SHOULDERS = "crop=340:191:85:10,scale=1280:720"
WHOLE_PHOTO = "scale=-2:720,pad=1280:720:(ow-iw)/2:0"
PAN_LEFT = "crop=340:191:'40+60*t':10,scale=1280:720"
ALLOWED_LEFTOVER_MB = 64

pytestmark = [
    pytest.mark.gpu,
    pytest.mark.skipif(
        shutil.which("ffmpeg") is None or not YOLO_WEIGHTS.exists() or not CLIP_WEIGHTS.exists(),
        reason="needs FFmpeg and the phase 2 weights from setup.bat",
    ),
]


def clip_of_photo(target: Path, chain: str, seconds: int = 2) -> Path:
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-loop",
            "1",
            "-t",
            str(seconds),
            "-r",
            "30",
            "-i",
            str(PHOTO),
            "-vf",
            chain,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(target),
        ],
        check=True,
    )
    return target


def clip_of_color(target: Path, color: str = "red") -> Path:
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:size=1280x720:rate=30:duration=2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(target),
        ],
        check=True,
    )
    return target


@pytest.fixture(scope="module")
def folder(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("photo_clips")


@pytest.fixture(scope="module")
def portrait(folder: Path) -> Path:
    return clip_of_photo(folder / "portrait.mp4", HEAD_AND_SHOULDERS)


@pytest.fixture(scope="module")
def gpu() -> GpuGuard:
    return NvmlGpuGuard()


@pytest.fixture(scope="module")
def detector(gpu: GpuGuard) -> ObjectDetector:
    return YoloObjectDetector(YOLO_WEIGHTS, gpu)


@pytest.fixture(scope="module")
def encoder(gpu: GpuGuard) -> ShotEncoder:
    return OpenClipEncoder(CLIP_WEIGHTS, AESTHETIC_WEIGHTS, gpu)


@pytest.fixture(scope="module")
def analyzed(portrait: Path, detector: ObjectDetector, encoder: ShotEncoder) -> ShotMeasure:
    sampler = OpenCvFrameSampler(FACE_MODEL)
    return AnalyzeShots(SceneDetectShots(), sampler, detector, encoder).run(portrait, 2.0)[0]


def test_b2_mediapipe_finds_a_real_face(portrait: Path) -> None:
    frames = OpenCvFrameSampler(FACE_MODEL).sample(portrait)

    assert all(frame.subject_area > 0.05 for frame in frames)


def test_b2_a_face_too_small_for_mediapipe_is_still_a_subject_through_yolo(
    folder: Path, detector: ObjectDetector
) -> None:
    whole = clip_of_photo(folder / "whole.mp4", WHOLE_PHOTO)
    frames = OpenCvFrameSampler(FACE_MODEL).sample(whole)
    people = [
        max((box.area for box in found.objects if box.label == "person"), default=0.0)
        for found in detector.detect_objects(whole)
    ]

    assert all(frame.subject_area == 0.0 for frame in frames)
    assert min(people) > 0.2


def test_b2_yolo_frames_line_up_with_the_sampler(portrait: Path, detector: ObjectDetector) -> None:
    frames = OpenCvFrameSampler(FACE_MODEL).sample(portrait)

    assert [found.time for found in detector.detect_objects(portrait)] == [
        frame.time for frame in frames
    ]


def test_b2_yolo_finds_a_real_person_in_normalized_boxes(
    portrait: Path, detector: ObjectDetector
) -> None:
    boxes = [box for found in detector.detect_objects(portrait) for box in found.objects]
    people = [box for box in boxes if box.label == "person"]

    assert people
    assert all(0.0 <= box.center_x <= 1.0 and 0.0 < box.width <= 1.0 for box in people)
    assert all(box.confidence >= 0.35 for box in people)


def test_b2_a_blank_clip_has_no_objects(folder: Path, detector: ObjectDetector) -> None:
    blank = clip_of_color(folder / "blank.mp4")

    assert all(found.objects == () for found in detector.detect_objects(blank))


def test_b2_clip_embeddings_are_unit_vectors_of_plain_floats(
    portrait: Path, encoder: ShotEncoder
) -> None:
    embedding = encoder.encode_shots(portrait, [(0.0, 2.0)])[0].embedding

    assert len(embedding) == 512
    assert type(embedding[0]) is float
    assert sum(value**2 for value in embedding) == pytest.approx(1.0, abs=0.001)


def test_b2_aesthetics_are_scaled_zero_to_one(portrait: Path, encoder: ShotEncoder) -> None:
    assert 0.0 < encoder.encode_shots(portrait, [(0.0, 2.0)])[0].aesthetics < 1.0


def test_b2_a_real_photo_outranks_a_blank_frame_on_aesthetics(
    folder: Path, portrait: Path, encoder: ShotEncoder
) -> None:
    blank = clip_of_color(folder / "gray.mp4", "gray")

    photo_score = encoder.encode_shots(portrait, [(0.0, 2.0)])[0].aesthetics
    blank_score = encoder.encode_shots(blank, [(0.0, 2.0)])[0].aesthetics

    assert photo_score > blank_score


def test_b2_a_span_with_no_frames_gets_an_empty_vision(
    portrait: Path, encoder: ShotEncoder
) -> None:
    filled, empty = encoder.encode_shots(portrait, [(0.0, 1.0), (50.0, 51.0)])

    assert len(filled.embedding) == 512
    assert empty.embedding == ()


def test_b2_two_clips_of_one_photo_are_duplicates_and_a_different_clip_is_not(
    folder: Path, portrait: Path, encoder: ShotEncoder
) -> None:
    copy = clip_of_photo(folder / "copy.mp4", HEAD_AND_SHOULDERS)
    other = clip_of_color(folder / "green.mp4", "green")

    first = encoder.encode_shots(portrait, [(0.0, 2.0)])[0].embedding
    second = encoder.encode_shots(copy, [(0.0, 2.0)])[0].embedding
    third = encoder.encode_shots(other, [(0.0, 2.0)])[0].embedding

    assert cosine_similarity(first, second) > DUPLICATE_SIMILARITY
    assert cosine_similarity(first, third) < DUPLICATE_SIMILARITY


def test_b4_text_search_separates_a_person_from_a_blank_frame(
    folder: Path, analyzed: ShotMeasure, encoder: ShotEncoder
) -> None:
    blank_clip = clip_of_color(folder / "blue.mp4", "blue")
    blank = analyzed.model_copy(
        update={"embedding": encoder.encode_shots(blank_clip, [(0.0, 2.0)])[0].embedding}
    )

    ranked = SearchShots(encoder).rank("person", [blank, analyzed])

    assert ranked[0].shot is analyzed
    assert ranked[0].matched is True


def test_b2_text_vectors_are_memoized_so_the_gpu_is_not_reloaded(gpu: GpuGuard) -> None:
    class CountingGuard:
        def __init__(self) -> None:
            self.sessions = 0

        def status(self) -> None:
            return None

        def loaded(self, load: Callable[[], T]) -> AbstractContextManager[T]:
            self.sessions += 1
            return gpu.loaded(load)

    counting = CountingGuard()
    fresh = OpenClipEncoder(CLIP_WEIGHTS, AESTHETIC_WEIGHTS, counting)

    first = fresh.encode_texts([tag_phrase("car")])
    second = fresh.encode_texts([tag_phrase("car")])

    assert first == second
    assert counting.sessions == 1


def test_b2_the_whole_analysis_measures_a_real_portrait(analyzed: ShotMeasure) -> None:
    assert "person" in analyzed.tags
    assert analyzed.subject > 0.5
    assert len(analyzed.embedding) == 512
    assert analyzed.dominant_color.startswith("#")
    assert score_shots([analyzed])[0].is_usable is True


def test_b2_a_pan_gives_a_real_direction_and_object_speed(
    folder: Path, detector: ObjectDetector, encoder: ShotEncoder
) -> None:
    pan = clip_of_photo(folder / "pan.mp4", PAN_LEFT)
    sampler = OpenCvFrameSampler(FACE_MODEL)

    measure = AnalyzeShots(SceneDetectShots(), sampler, detector, encoder).run(pan, 2.0)[0]

    assert measure.motion_direction is MotionDirection.LEFT
    assert measure.action > 0.0


def test_b2_a_solid_red_clip_has_a_red_dominant_color(folder: Path) -> None:
    red = clip_of_color(folder / "red.mp4")

    frames = OpenCvFrameSampler(FACE_MODEL).sample(red)

    assert frames[0].color.startswith("#f")
    assert frames[0].color[3:] in {"1010", "0010", "1000"}


def test_rule_4_yolo_leaves_no_model_on_the_gpu(portrait: Path, detector: ObjectDetector) -> None:
    detector.detect_objects(portrait)
    gc.collect()

    assert torch.cuda.memory_allocated() / 1024**2 < ALLOWED_LEFTOVER_MB


def test_rule_4_clip_leaves_no_model_on_the_gpu(portrait: Path, encoder: ShotEncoder) -> None:
    encoder.encode_shots(portrait, [(0.0, 2.0)])
    gc.collect()

    assert torch.cuda.memory_allocated() / 1024**2 < ALLOWED_LEFTOVER_MB


def test_rule_3_ultralytics_is_pinned_inside_the_project_and_offline(
    portrait: Path, detector: ObjectDetector
) -> None:
    detector.detect_objects(portrait)
    from ultralytics import utils

    assert Path(utils.USER_CONFIG_DIR).is_relative_to(MODELS)
    assert utils.ONLINE is False


def test_a_missing_weight_file_is_a_clear_error(portrait: Path, gpu: GpuGuard) -> None:
    missing = YoloObjectDetector(MODELS / "yolo" / "missing.pt", gpu)

    with pytest.raises(AnalysisError, match="setup.bat"):
        missing.detect_objects(portrait)
