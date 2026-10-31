"""Composition root: builds adapters and hands them to the app.

Spec: specs/11-coding-standards.md#4
"""

from __future__ import annotations

from fastapi import FastAPI

from app.adapters.beat_this_tracker import BeatThisTracker
from app.adapters.clip_encoder import OpenClipEncoder
from app.adapters.ffmpeg_audio import FfmpegAudioDecoder
from app.adapters.ffmpeg_audio_finisher import FfmpegAudioFinisher
from app.adapters.ffmpeg_compositor import FfmpegCompositor
from app.adapters.ffmpeg_frame_media import FfmpegFrameMedia, FfmpegVideoUpscaler
from app.adapters.ffmpeg_media_tools import FfmpegMediaTools
from app.adapters.ffmpeg_probe import FfmpegProbe
from app.adapters.file_cache import FileCache
from app.adapters.http_backend_notifier import HttpBackendNotifier
from app.adapters.librosa_curves import LibrosaCurveExtractor
from app.adapters.nvml_gpu_guard import NvmlGpuGuard
from app.adapters.nvml_thermal_guard import NvmlThermalGuard
from app.adapters.ollama_llm import OllamaLlmClient
from app.adapters.opencv_frame_sampler import OpenCvFrameSampler
from app.adapters.realesrgan_upscaler import RealEsrganUpscaler
from app.adapters.rife_interpolator import RifeInterpolator
from app.adapters.scenedetect_shots import SceneDetectShots
from app.adapters.xxhash_hasher import XxhashHasher
from app.adapters.yolo_detector import YoloObjectDetector
from app.api.routes import create_api
from app.application.analyze_asset import AnalyzeAsset
from app.application.analyze_music import AnalyzeMusic
from app.application.analyze_shots import AnalyzeShots
from app.application.direct_edit import DirectEdit
from app.application.job_runner import JobRunner
from app.application.render_job import RenderEdit
from app.config import Settings
from app.logging_setup import configure_logging


def build_app() -> FastAPI:
    settings = Settings()  # type: ignore[call-arg]  # values come from config/local.env
    configure_logging(settings.resolved(settings.logs_dir))
    notifier = HttpBackendNotifier.create(settings.backend_url, settings.worker_token)
    media_root = settings.resolved(settings.media_dir)
    tools = FfmpegMediaTools()
    models = settings.resolved(settings.models_dir)
    checkpoint = models / "beat_this" / "small0.ckpt"
    music = AnalyzeMusic(FfmpegAudioDecoder(), BeatThisTracker(checkpoint), LibrosaCurveExtractor())
    gpu = NvmlGpuGuard()
    shots = AnalyzeShots(
        SceneDetectShots(),
        OpenCvFrameSampler(models / "mediapipe" / "blaze_face_short_range.tflite"),
        YoloObjectDetector(models / "yolo" / "yolo11n.pt", gpu),
        OpenClipEncoder(
            models / "clip" / "vit_b_32_openai.safetensors",
            models / "clip" / "sa_0_4_vit_b_32_linear.pth",
            gpu,
        ),
    )
    cache = FileCache(media_root)
    director = DirectEdit(OllamaLlmClient.create(settings.ollama_url), gpu)
    render_edit = RenderEdit(
        media_root,
        cache,
        cache,
        FfmpegCompositor(),
        FfmpegAudioFinisher(),
        notifier,
        director,
        thermal=NvmlThermalGuard(gpu),
        interpolator=RifeInterpolator(gpu, models / "rife" / "flownet_v4.25.pkl"),
        frames=FfmpegFrameMedia(),
        upscaler=FfmpegVideoUpscaler(
            RealEsrganUpscaler(gpu, models / "realesrgan" / "realesr-general-x4v3.pth")
        ),
    )
    analyze_asset = AnalyzeAsset(
        media_root,
        FfmpegProbe(),
        XxhashHasher(),
        cache,
        tools,
        tools,
        notifier,
        music,
        shots,
    )
    return create_api(
        runner=JobRunner(notifier),
        gpu=gpu,
        analyze=analyze_asset.run,
        render=render_edit.run,
        token=settings.worker_token,
    )


app = build_app()
