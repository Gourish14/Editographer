package com.editographer.worker.domain;

/** Port for calling the Python worker. Spec: specs/07-api-and-data.md#worker-api */
public interface WorkerClient {

  /** True when the worker answers and is not busy. An unreachable worker counts as not idle. */
  boolean isIdle();

  /** Sends an analysis job. Throws ApiException with WORKER_UNAVAILABLE if it cannot. */
  void submitAnalyze(AnalyzeJobRequest request);
}
