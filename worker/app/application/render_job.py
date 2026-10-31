"""Runs a render from plan to final file. Spec: specs/04-pipeline.md"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath

import structlog

from app.application.cool_mode import CoolDown, cool_compositor
from app.application.direct_edit import DirectEdit
from app.application.enhance_stages import (
    RetimeStage,
    UpscaleStage,
    needs_rife,
    raises_fps,
    working_size,
)
from app.application.job_runner import CancellationToken
from app.application.look import audio_mix, segment_look
from app.domain.analysis import StoredAnalysis
from app.domain.brain.planner import ClipInput, build_edit_plan
from app.domain.brain.text_rules import TextItem as OverlayItem
from app.domain.errors import ErrorCode, RenderError
from app.domain.models import AssetInput, AssetType, RenderJob
from app.domain.photo import PhotoAnalysis
from app.domain.plan import EditPlan
from app.ports.backend_notifier import BackendNotifier
from app.ports.enhance import FrameSize, Interpolator
from app.ports.frames import FrameMedia, UpscaleSpec, VideoUpscaler
from app.ports.media import AnalysisCache
from app.ports.render import (
    AudioFinisher,
    Compositor,
    EncodeProfile,
    PlanStore,
    SegmentLook,
    TextOverlay,
)
from app.ports.thermal import ThermalGuard

log = structlog.get_logger()

RENDERS_FOLDER = "renders"
WORK_FOLDER = "work"
PREVIEW_FILE = "preview.mp4"
FINAL_FILE = "final.mp4"
PREVIEW_LONG_EDGE = 1920
PREVIEW_QUALITY = 28
PREVIEW_PRESET = "p2"
FINAL_QUALITY = 19
FINAL_PRESET = "p5"

STAGE_PLANNING = "PLANNING"
STAGE_COMPOSING = "COMPOSING"
STAGE_ENCODING = "ENCODING"
STAGE_DELIVER = "DELIVER"
STAGE_UPSCALING = "UPSCALING"
MODE_MAX = "max"
COMPOSE_SHARE_MAX = 30
UPSCALE_SHARE_MAX = 35
ALL_SHARES_MAX = 90
UPSCALE_REPORT_EVERY_FRAMES = 10

DIRECTOR_PERCENT = 2
DIRECTOR_MESSAGE = "Asking the AI director"
PLANNED_PERCENT = 5
PREVIEW_DONE_PERCENT = 20
FINAL_DONE_PERCENT = 90
ENCODED_PERCENT = 95


class RenderEdit:
    def __init__(
        self,
        media_root: Path,
        cache: AnalysisCache,
        plans: PlanStore,
        compositor: Compositor,
        audio: AudioFinisher,
        notifier: BackendNotifier,
        director: DirectEdit,
        thermal: ThermalGuard | None = None,
        interpolator: Interpolator | None = None,
        frames: FrameMedia | None = None,
        upscaler: VideoUpscaler | None = None,
        text: TextOverlay | None = None,
    ) -> None:
        self._media_root = media_root
        self._cache = cache
        self._plans = plans
        self._compositor = compositor
        self._audio = audio
        self._notifier = notifier
        self._director = director
        self._thermal = thermal
        self._interpolator = interpolator
        self._frames = frames
        self._upscaler = upscaler
        self._text = text

    def run(self, job: RenderJob, token: CancellationToken) -> None:
        self._notifier.progress(job.job_id, STAGE_PLANNING, 1)
        plan = self._plan(job, token)
        self._plans.save_plan(job.render_id, plan)
        self._notifier.progress(job.job_id, STAGE_PLANNING, PLANNED_PERCENT)
        token.raise_if_cancelled()

        folder = self._media_root / RENDERS_FOLDER / job.render_id
        folder.mkdir(parents=True, exist_ok=True)
        sources = {asset.id: self._media_root / asset.path for asset in job.assets}
        music = sources[plan.music.asset_id]

        retimed: dict[str, Path] = {}  # RIFE frames are made once, for preview and final
        preview = folder / PREVIEW_FILE
        self._render_pass(
            job, plan, sources, _preview_profile(plan), music, preview, token,
            PLANNED_PERCENT, PREVIEW_DONE_PERCENT, _Stages(retimed),
        )  # fmt: skip
        self._notifier.preview_ready(job.job_id, self._relative(preview))

        final = folder / FINAL_FILE
        if plan.output.mode == "preview":
            shutil.copyfile(preview, final)
        else:
            profile, stages = self._final_stages(job, plan, retimed)
            self._render_pass(
                job, plan, sources, profile, music, final, token,
                PREVIEW_DONE_PERCENT, FINAL_DONE_PERCENT, stages,
            )  # fmt: skip

        self._notifier.progress(job.job_id, STAGE_DELIVER, ENCODED_PERCENT)
        shutil.rmtree(folder / WORK_FOLDER, ignore_errors=True)
        self._notifier.job_done(
            job.job_id, self._relative(final), plan.model_dump(mode="json", by_alias=True)
        )

    def _final_stages(
        self, job: RenderJob, plan: EditPlan, retimed: dict[str, Path]
    ) -> tuple[EncodeProfile, _Stages]:
        """Max quality composes at the size the sources hold and upscales to the output size."""
        profile = _final_profile(plan)
        if plan.output.mode != MODE_MAX or self._upscaler is None:
            return profile, _Stages(retimed)
        size = working_size(plan, {asset.id: asset for asset in job.assets})
        if not size.upscale:
            return profile, _Stages(retimed)
        working = replace(profile, width=size.width, height=size.height, sharpen=False)
        return working, _Stages(retimed, FrameSize(profile.width, profile.height))

    def _plan(self, job: RenderJob, token: CancellationToken) -> EditPlan:
        tracks = [asset for asset in job.assets if asset.type is AssetType.MUSIC]
        clips = [asset for asset in job.assets if asset.type is AssetType.VIDEO]
        photos = [asset for asset in job.assets if asset.type is AssetType.PHOTO]
        if not tracks or not (clips or photos):
            raise RenderError(
                "A render needs an analyzed song and a clip or photo", ErrorCode.PLAN_INVALID
            )
        song = max(tracks, key=lambda asset: asset.duration_sec or 0.0)
        music = self._analysis(song).music
        if music is None:
            raise RenderError(f"No music map for {song.id}", ErrorCode.PLAN_INVALID)
        inputs = [ClipInput(clip.id, self._analysis(clip)) for clip in clips]
        if self._director.has_work(job.settings):
            token.raise_if_cancelled()
            self._notifier.progress(job.job_id, STAGE_PLANNING, DIRECTOR_PERCENT, DIRECTOR_MESSAGE)
        direction = self._director.decide(music, inputs, job.settings)
        token.raise_if_cancelled()
        photo_inputs = [ClipInput(photo.id, self._analysis(photo)) for photo in photos]
        return build_edit_plan(song.id, music, inputs, job.settings, direction, photo_inputs)

    def _analysis(self, asset: AssetInput) -> StoredAnalysis:
        file_hash = PurePosixPath(asset.analysis_path or "").parent.name
        analysis = self._cache.load(file_hash)
        if analysis is None:
            raise RenderError(f"No analysis for {asset.id}", ErrorCode.PLAN_INVALID)
        return analysis

    def _render_pass(
        self,
        job: RenderJob,
        plan: EditPlan,
        sources: dict[str, Path],
        profile: EncodeProfile,
        music: Path,
        target: Path,
        token: CancellationToken,
        first_percent: int,
        last_percent: int,
        stages: _Stages | None = None,
    ) -> None:
        stages = stages or _Stages({})
        work = target.parent / WORK_FOLDER / target.stem
        work.mkdir(parents=True, exist_ok=True)
        compose_end, upscale_end = _stage_ends(first_percent, last_percent, stages.upscale_to)
        report = _progress_reporter(self._notifier, job.job_id, first_percent, compose_end)
        self._retime(job, plan, sources, work.parent, token, stages.retimed)
        compositor = cool_compositor(self._compositor, self._thermal, job.settings.cool_mode, token)
        photos = self._photo_analyses(job)
        parts = []
        counts = frame_counts(plan)
        total_frames = sum(counts)
        for index, (segment, frames) in enumerate(zip(plan.segments, counts, strict=True)):
            token.raise_if_cancelled()
            part = work / f"{segment.id}.mp4"
            look = replace(
                segment_look(plan, index, sources), retimed=stages.retimed.get(segment.id)
            )
            compositor.render_segment(
                sources[segment.asset_id],
                segment,
                frames,
                profile,
                part,
                _with_photo(look, photos.get(segment.asset_id)),
            )
            parts.append(part)
            report(index + 1, len(plan.segments))
        token.raise_if_cancelled()

        self._notifier.progress(job.job_id, STAGE_ENCODING, compose_end)
        joined = work / "joined.mp4"
        self._compositor.join(parts, joined)
        picture = joined
        if plan.text and self._text is not None:
            picture = work / "titled.mp4"
            self._text.overlay_text(
                joined,
                _overlay_items(plan),
                profile,
                total_frames,
                picture,
            )
        if stages.upscale_to is not None and self._upscaler is not None:
            picture = self._upscale(
                job, picture, work, profile, stages.upscale_to, total_frames, token,
                (compose_end, upscale_end),
            )  # fmt: skip
        self._notifier.progress(job.job_id, STAGE_ENCODING, upscale_end)
        self._audio.add_music(
            picture,
            music,
            plan.music.start,
            plan.music.end - plan.music.start,
            target,
            audio_mix(plan, sources),
        )

    def _retime(
        self,
        job: RenderJob,
        plan: EditPlan,
        sources: dict[str, Path],
        work: Path,
        token: CancellationToken,
        retimed: dict[str, Path],
    ) -> None:
        pending = [
            (segment, sources[segment.asset_id], frames)
            for segment, frames in zip(plan.segments, frame_counts(plan), strict=True)
            if segment.id not in retimed
            and (
                needs_rife(segment)
                or (plan.output.mode == MODE_MAX and raises_fps(segment, plan.output.fps))
            )
        ]
        if not pending:
            return
        if self._interpolator is None or self._frames is None:
            log.warning("render.rife_missing", segments=len(pending))
            return

        def report(done: int, total: int) -> None:
            self._notifier.progress(
                job.job_id, STAGE_COMPOSING, PLANNED_PERCENT, f"Slow motion {done} of {total}"
            )

        stage = RetimeStage(self._interpolator, self._frames, self._cool_down(job, token))
        retimed.update(stage.run(pending, plan.output.fps, work, token, report))

    def _upscale(
        self,
        job: RenderJob,
        joined: Path,
        work: Path,
        profile: EncodeProfile,
        size: FrameSize,
        frames: int,
        token: CancellationToken,
        percents: tuple[int, int],
    ) -> Path:
        assert self._upscaler is not None
        target = work / "upscaled.mp4"
        spec = UpscaleSpec(
            joined, target, FrameSize(profile.width, profile.height), size, frames,
            profile.fps, FINAL_QUALITY, FINAL_PRESET, job.settings.cool_mode,
        )  # fmt: skip
        first, last = percents

        def report(done: int, total: int) -> None:
            if done % UPSCALE_REPORT_EVERY_FRAMES == 0 or done == total:
                percent = first + (last - first) * done // total
                self._notifier.progress(
                    job.job_id, STAGE_UPSCALING, percent, f"Frame {done} of {total}"
                )

        UpscaleStage(self._upscaler, self._cool_down(job, token)).run(spec, token, report)
        return target

    def _cool_down(self, job: RenderJob, token: CancellationToken) -> CoolDown | None:
        if job.settings.cool_mode and self._thermal is not None:
            return CoolDown(self._thermal, token)
        return None

    def _photo_analyses(self, job: RenderJob) -> dict[str, PhotoAnalysis]:
        found = {
            asset.id: self._analysis(asset).photo
            for asset in job.assets
            if asset.type is AssetType.PHOTO
        }
        return {asset_id: photo for asset_id, photo in found.items() if photo is not None}

    def _relative(self, path: Path) -> str:
        return path.relative_to(self._media_root).as_posix()


@dataclass(frozen=True)
class _Stages:
    """What one pass shares with the others: RIFE frames made so far, and the upscale target."""

    retimed: dict[str, Path]
    upscale_to: FrameSize | None = None


def _stage_ends(first: int, last: int, upscale_to: FrameSize | None) -> tuple[int, int]:
    """Where compose and upscale end. Spec 04 weights Max as compose 30, upscale 35, rest 25."""
    if upscale_to is None:
        return last, last
    span = last - first
    compose_end = first + span * COMPOSE_SHARE_MAX // ALL_SHARES_MAX
    upscale_end = first + span * (COMPOSE_SHARE_MAX + UPSCALE_SHARE_MAX) // ALL_SHARES_MAX
    return compose_end, upscale_end


def _with_photo(look: SegmentLook, photo: PhotoAnalysis | None) -> SegmentLook:
    return look if photo is None else replace(look, photo=photo)


def _overlay_items(plan: EditPlan) -> list[OverlayItem]:
    """Text times on the edit's own clock, from its first frame."""
    return [
        OverlayItem(
            item.content,
            round(item.at - plan.music.start, 4),
            item.duration,
            item.anim,
            item.behind_subject,
        )
        for item in plan.text
    ]


def cut_frames(plan: EditPlan) -> list[int]:
    """The frame of every cut plus the end of the edit, all counted from the start of the edit."""
    fps = plan.output.fps
    start = plan.music.start
    edges = [segment.at for segment in plan.segments] + [plan.music.end]
    return [round((edge - start) * fps) for edge in edges]


def frame_counts(plan: EditPlan) -> list[int]:
    """Each segment fills the space to the next cut, so the sum is the edit, frame for frame."""
    cuts = cut_frames(plan)
    return [later - earlier for earlier, later in zip(cuts, cuts[1:], strict=False)]


def _preview_profile(plan: EditPlan) -> EncodeProfile:
    output = plan.output
    scale = PREVIEW_LONG_EDGE / max(output.width, output.height)
    return EncodeProfile(
        width=_even(output.width * scale),
        height=_even(output.height * scale),
        fps=output.fps,
        quality=PREVIEW_QUALITY,
        preset=PREVIEW_PRESET,
        sharpen=False,
    )


def _final_profile(plan: EditPlan) -> EncodeProfile:
    output = plan.output
    return EncodeProfile(
        width=output.width,
        height=output.height,
        fps=output.fps,
        quality=FINAL_QUALITY,
        preset=FINAL_PRESET,
        sharpen=True,
    )


def _even(value: float) -> int:
    return round(value / 2) * 2


def _progress_reporter(
    notifier: BackendNotifier, job_id: str, first: int, last: int
) -> Callable[[int, int], None]:
    def report(done: int, total: int) -> None:
        percent = first + (last - first) * done // total
        notifier.progress(job_id, STAGE_COMPOSING, percent, f"Segment {done} of {total}")

    return report
