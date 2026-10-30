package com.editographer.worker.domain;

import java.util.Optional;
import java.util.UUID;

/** Port for calling the Python worker. Spec: specs/07-api-and-data.md#worker-api */
public interface WorkerClient {

  /** The worker's status, or empty when it cannot be reached. */
  Optional<WorkerStatus> status();

  /** True when the worker answers and is not busy. */
  default boolean isIdle() {
    return status().filter(status -> !status.busy()).isPresent();
  }

  /** Sends an analysis job. Throws ApiException with WORKER_UNAVAILABLE if it cannot. */
  void submitAnalyze(AnalyzeJobRequest request);

  /** Sends a render job. Throws ApiException with WORKER_UNAVAILABLE if it cannot. */
  void submitRender(RenderJobRequest request);

  /** Asks the worker to stop after its current stage. */
  void cancel(UUID jobId);
}
