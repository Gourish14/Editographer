package com.editographer.asset.domain;

import java.util.Objects;

/**
 * What the worker learned about an asset. Spec:
 * specs/07-api-and-data.md#internal-worker--backend-header-x-worker-token
 */
public record AnalysisResult(
    String analysisPath,
    String fileHash,
    String cameraMode,
    String logProfile,
    Double durationSec,
    Integer width,
    Integer height,
    Double fps) {

  public AnalysisResult {
    Objects.requireNonNull(analysisPath, "analysisPath");
  }
}
