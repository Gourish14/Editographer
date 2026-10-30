package com.editographer.asset.domain;

/** Progress of an asset's analysis job. Spec: specs/07-api-and-data.md */
public enum AnalysisStatus {
  PENDING,
  RUNNING,
  DONE,
  FAILED
}
