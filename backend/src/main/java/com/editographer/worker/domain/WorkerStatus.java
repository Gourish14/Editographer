package com.editographer.worker.domain;

/** What GET /health reports. Spec: specs/07-api-and-data.md#worker-api */
public record WorkerStatus(boolean busy, String currentJobId, Gpu gpu) {

  /** The worker's GPU. Null when it cannot read NVML. */
  public record Gpu(String name, Long vramFreeMb, Integer tempC) {}
}
