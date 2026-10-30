package com.editographer.render.domain;

import com.editographer.storage.domain.MediaPath;
import java.time.Instant;
import java.util.Objects;

/** How far a render has got. Plan and log are JSON documents kept as text. */
public record RenderState(
    RenderStatus status,
    String stage,
    int progress,
    String log,
    String editPlan,
    MediaPath previewPath,
    MediaPath outputPath,
    String error,
    Instant finishedAt) {

  private static final int COMPLETE = 100;

  public RenderState {
    Objects.requireNonNull(status, "status");
    if (progress < 0 || progress > COMPLETE) {
      throw new IllegalArgumentException("progress must be between 0 and 100");
    }
  }

  static RenderState queued() {
    return new RenderState(RenderStatus.QUEUED, null, 0, null, null, null, null, null, null);
  }

  RenderState progressed(RenderStatus newStatus, String newStage, int percent) {
    return new RenderState(
        newStatus, newStage, percent, log, editPlan, previewPath, outputPath, error, finishedAt);
  }

  RenderState withPreview(MediaPath path) {
    return new RenderState(
        status, stage, progress, log, editPlan, path, outputPath, error, finishedAt);
  }

  RenderState done(MediaPath output, String plan, Instant now) {
    return new RenderState(
        RenderStatus.DONE, stage, COMPLETE, log, plan, previewPath, output, error, now);
  }

  RenderState ended(RenderStatus finalStatus, String message, Instant now) {
    return new RenderState(
        finalStatus, stage, progress, log, editPlan, previewPath, outputPath, message, now);
  }
}
