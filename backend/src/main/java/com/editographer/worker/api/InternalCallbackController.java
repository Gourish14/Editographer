package com.editographer.worker.api;

import com.editographer.asset.domain.AnalysisResult;
import com.editographer.asset.domain.AssetId;
import com.editographer.job.domain.JobStatus;
import com.editographer.storage.domain.MediaPath;
import com.editographer.worker.api.dto.AssetAnalyzedRequest;
import com.editographer.worker.api.dto.JobCompleteRequest;
import com.editographer.worker.api.dto.PreviewReadyRequest;
import com.editographer.worker.api.dto.ProgressRequest;
import com.editographer.worker.application.JobCompletion;
import com.editographer.worker.application.WorkerCallbackService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/**
 * Callbacks from the worker. Spec:
 * specs/07-api-and-data.md#internal-worker--backend-header-x-worker-token
 */
@RestController
@RequestMapping("/internal")
public final class InternalCallbackController {

  private final WorkerCallbackService callbacks;

  public InternalCallbackController(WorkerCallbackService callbacks) {
    this.callbacks = callbacks;
  }

  @PostMapping("/progress")
  @ResponseStatus(HttpStatus.NO_CONTENT)
  public void progress(@Valid @RequestBody ProgressRequest request) {
    callbacks.progress(request.jobId(), request.stage(), request.percent(), request.message());
  }

  @PostMapping("/asset-analyzed")
  @ResponseStatus(HttpStatus.NO_CONTENT)
  public void assetAnalyzed(@Valid @RequestBody AssetAnalyzedRequest request) {
    callbacks.assetAnalyzed(
        new AssetId(request.assetId()),
        new AnalysisResult(
            request.analysisPath(),
            request.fileHash(),
            request.cameraMode(),
            request.logProfile(),
            request.durationSec(),
            request.width(),
            request.height(),
            request.fps()));
  }

  @PostMapping("/preview-ready")
  @ResponseStatus(HttpStatus.NO_CONTENT)
  public void previewReady(@Valid @RequestBody PreviewReadyRequest request) {
    callbacks.previewReady(request.jobId(), new MediaPath(request.path()));
  }

  @PostMapping("/complete")
  @ResponseStatus(HttpStatus.NO_CONTENT)
  public void complete(@Valid @RequestBody JobCompleteRequest request) {
    callbacks.jobCompleted(
        new JobCompletion(
            request.jobId(),
            JobStatus.valueOf(request.status()),
            request.outputPath() == null ? null : new MediaPath(request.outputPath()),
            request.plan() == null ? null : request.plan().toString(),
            request.error()));
  }
}
