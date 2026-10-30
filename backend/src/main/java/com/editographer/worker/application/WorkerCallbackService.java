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
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Applies what the worker reports back. Spec: specs/07-api-and-data.md#job-flow */
@Service
public class WorkerCallbackService {

  private final AssetRepository assets;
  private final JobQueue queue;

  public WorkerCallbackService(AssetRepository assets, JobQueue queue) {
    this.assets = assets;
    this.queue = queue;
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
  public void jobCompleted(UUID jobId, JobStatus status) {
    Job job =
        queue
            .findById(jobId)
            .orElseThrow(
                () -> new ApiException(ErrorCode.JOB_NOT_FOUND, "Job " + jobId + " not found"));
    queue.finish(jobId, status);
    if (job.kind() == JobKind.ANALYZE && status == JobStatus.FAILED) {
      AssetId assetId = new AssetId(job.refId());
      assets
          .findById(assetId)
          .ifPresent(asset -> assets.save(asset.withAnalysisStatus(AnalysisStatus.FAILED)));
    }
  }
}
