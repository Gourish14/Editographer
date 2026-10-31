"""Runs a render from plan to final file. Spec: specs/04-pipeline.md"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path, PurePosixPath

import structlog

from app.application.job_runner import CancellationToken
from app.domain.analysis import StoredAnalysis
from app.domain.brain.planner import ClipInput, build_edit_plan
from app.domain.errors import ErrorCode, RenderError
from app.domain.models import AssetInput, AssetType, RenderJob
from app.domain.plan import EditPlan
from app.ports.backend_notifier import BackendNotifier
from app.ports.media import AnalysisCache
from app.ports.render import AudioFinisher, Compositor, EncodeProfile, PlanStore

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
    ) -> None:
        self._media_root = media_root
        self._cache = cache
        self._plans = plans
        self._compositor = compositor
        self._audio = audio
        self._notifier = notifier

    def run(self, job: RenderJob, token: CancellationToken) -> None:
        self._notifier.progress(job.job_id, STAGE_PLANNING, 1)
        plan = self._plan(job)
        self._plans.save_plan(job.render_id, plan)
        self._notifier.progress(job.job_id, STAGE_PLANNING, PLANNED_PERCENT)
        token.raise_if_cancelled()

        folder = self._media_root / RENDERS_FOLDER / job.render_id
        folder.mkdir(parents=True, exist_ok=True)
        sources = {asset.id: self._media_root / asset.path for asset in job.assets}
        music = sources[plan.music.asset_id]

        preview = folder / PREVIEW_FILE
        self._render_pass(
            job, plan, sources, _preview_profile(plan), music, preview, token,
            PLANNED_PERCENT, PREVIEW_DONE_PERCENT,
        )  # fmt: skip
        self._notifier.preview_ready(job.job_id, self._relative(preview))

        final = folder / FINAL_FILE
        if plan.output.mode == "preview":
            shutil.copyfile(preview, final)
        else:
            self._render_pass(
                job, plan, sources, _final_profile(plan), music, final, token,
                PREVIEW_DONE_PERCENT, FINAL_DONE_PERCENT,
            )  # fmt: skip

        self._notifier.progress(job.job_id, STAGE_DELIVER, ENCODED_PERCENT)
        shutil.rmtree(folder / WORK_FOLDER, ignore_errors=True)
        self._notifier.job_done(
            job.job_id, self._relative(final), plan.model_dump(mode="json", by_alias=True)
        )

    def _plan(self, job: RenderJob) -> EditPlan:
        tracks = [asset for asset in job.assets if asset.type is AssetType.MUSIC]
        clips = [asset for asset in job.assets if asset.type is AssetType.VIDEO]
        if not tracks or not clips:
            raise RenderError("A render needs an analyzed song and clip", ErrorCode.PLAN_INVALID)
        song = max(tracks, key=lambda asset: asset.duration_sec or 0.0)
        music = self._analysis(song).music
        if music is None:
            raise RenderError(f"No music map for {song.id}", ErrorCode.PLAN_INVALID)
        inputs = [ClipInput(clip.id, self._analysis(clip)) for clip in clips]
        return build_edit_plan(song.id, music, inputs, job.settings)

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
    ) -> None:
        work = target.parent / WORK_FOLDER / target.stem
        work.mkdir(parents=True, exist_ok=True)
        report = _progress_reporter(self._notifier, job.job_id, first_percent, last_percent)
        parts = []
        counts = frame_counts(plan)
        for index, (segment, frames) in enumerate(zip(plan.segments, counts, strict=True)):
            token.raise_if_cancelled()
            part = work / f"{segment.id}.mp4"
            self._compositor.render_segment(
                sources[segment.asset_id], segment, frames, profile, part
            )
            parts.append(part)
            report(index + 1, len(plan.segments))
        token.raise_if_cancelled()

        self._notifier.progress(job.job_id, STAGE_ENCODING, last_percent)
        joined = work / "joined.mp4"
        self._compositor.join(parts, joined)
        self._audio.add_music(
            joined, music, plan.music.start, plan.music.end - plan.music.start, target
        )

    def _relative(self, path: Path) -> str:
        return path.relative_to(self._media_root).as_posix()


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
