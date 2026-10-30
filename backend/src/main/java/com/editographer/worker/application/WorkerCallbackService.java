package com.editographer.worker.application;

import com.editographer.asset.domain.AnalysisResult;
import com.editographer.asset.domain.AnalysisStatus;
import com.editographer.asset.domain.Asset;
import com.editographer.asset.domain.AssetId;
import com.editographer.asset.domain.AssetRepository;
import com.editographer.common.error.ApiException;
import com.editographer.common.error.ErrorCode;
import com.editographer.job.domain.Job;
import com.editographer.job.domain.JobKind;
import com.editographer.job.domain.JobQueue;
import com.editographer.job.domain.JobStatus;
import com.editographer.render.application.RenderProgressService;
import com.editographer.render.domain.RenderId;
import com.editographer.storage.domain.MediaPath;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Applies what the worker reports back. Spec: specs/07-api-and-data.md#job-flow */
@Service
public class WorkerCallbackService {

  private static final String NO_OUTPUT_ERROR = "The worker finished without an output file";

  private final AssetRepository assets;
  private final JobQueue queue;
  private final RenderProgressService renders;

  public WorkerCallbackService(
      AssetRepository assets, JobQueue queue, RenderProgressService renders) {
    this.assets = assets;
    this.queue = queue;
    this.renders = renders;
  }

  @Transactional
  public void assetAnalyzed(AssetId id, AnalysisResult result) {
    Asset asset =
        assets
            .findById(id)
            .orElseThrow(
                () ->
                    new ApiException(
                        ErrorCode.ASSET_NOT_FOUND, "Asset " + id.value() + " not found"));
    assets.save(asset.withAnalysis(result));
  }

  @Transactional
  public void progress(UUID jobId, String stage, int percent, String message) {
    Job job = find(jobId);
    if (job.kind() == JobKind.RENDER) {
      renders.progress(new RenderId(job.refId()), stage, percent, message);
    }
  }

  @Transactional
  public void previewReady(UUID jobId, MediaPath path) {
    Job job = find(jobId);
    if (job.kind() == JobKind.RENDER) {
      renders.previewReady(new RenderId(job.refId()), path);
    }
  }

  @Transactional
  public void jobCompleted(JobCompletion completion) {
    Job job = find(completion.jobId());
    queue.finish(job.id(), completion.status());
    if (job.kind() == JobKind.RENDER) {
      completeRender(new RenderId(job.refId()), completion);
    } else if (completion.status() == JobStatus.FAILED) {
      assets
          .findById(new AssetId(job.refId()))
          .ifPresent(asset -> assets.save(asset.withAnalysisStatus(AnalysisStatus.FAILED)));
    }
  }

  private void completeRender(RenderId id, JobCompletion completion) {
    if (completion.status() == JobStatus.FAILED) {
      renders.failed(id, completion.error());
    } else if (completion.outputPath() == null) {
      renders.failed(id, NO_OUTPUT_ERROR);
    } else {
      renders.completed(id, completion.outputPath(), completion.plan());
    }
  }

  private Job find(UUID jobId) {
    return queue
        .findById(jobId)
        .orElseThrow(
            () -> new ApiException(ErrorCode.JOB_NOT_FOUND, "Job " + jobId + " not found"));
  }
}
