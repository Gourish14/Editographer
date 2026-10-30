package com.editographer.render.domain;

import java.util.Arrays;
import java.util.Optional;

/** Lifecycle of a render. Spec: specs/07-api-and-data.md */
public enum RenderStatus {
  QUEUED,
  ANALYZING,
  PLANNING,
  COMPOSING,
  UPSCALING,
  ENCODING,
  DONE,
  FAILED,
  CANCELLED;

  public boolean isFinished() {
    return this == DONE || this == FAILED || this == CANCELLED;
  }

  /** The working status a worker stage name stands for, if any. */
  public static Optional<RenderStatus> forStage(String stage) {
    return Arrays.stream(values())
        .filter(status -> !status.isFinished() && status.name().equals(stage))
        .findFirst();
  }
}
