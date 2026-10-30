package com.editographer.render.domain;

import com.editographer.project.domain.ProjectId;
import com.editographer.storage.domain.MediaPath;
import java.time.Instant;
import java.util.Objects;

/** One render request and its outcome. Spec: specs/07-api-and-data.md#job-flow */
public record Render(
    RenderId id,
    ProjectId projectId,
    RenderSettings settings,
    RenderState state,
    Instant createdAt) {

  private static final String RENDERS_FOLDER = "renders";

  public Render {
    Objects.requireNonNull(id, "id");
    Objects.requireNonNull(projectId, "projectId");
    Objects.requireNonNull(settings, "settings");
    Objects.requireNonNull(state, "state");
    Objects.requireNonNull(createdAt, "createdAt");
  }

  public static Render queued(ProjectId projectId, RenderSettings settings, Instant now) {
    return new Render(RenderId.newId(), projectId, settings, RenderState.queued(), now);
  }

  /** The folder that holds a render's preview, final file and plan. */
  public static MediaPath folder(RenderId id) {
    return new MediaPath(RENDERS_FOLDER + "/" + id.value());
  }

  /** Applies a progress report. A stage that names no status keeps the current status. */
  public Render progressed(String stage, int percent) {
    RenderStatus status = RenderStatus.forStage(stage).orElse(state.status());
    return with(state.progressed(status, stage, percent));
  }

  public Render withPreview(MediaPath path) {
    return with(state.withPreview(path));
  }

  public Render done(MediaPath output, String plan, Instant now) {
    return with(state.done(output, plan, now));
  }

  public Render failed(String error, Instant now) {
    return with(state.ended(RenderStatus.FAILED, error, now));
  }

  public Render cancelled(Instant now) {
    return with(state.ended(RenderStatus.CANCELLED, state.error(), now));
  }

  public boolean isFinished() {
    return state.status().isFinished();
  }

  private Render with(RenderState newState) {
    return new Render(id, projectId, settings, newState, createdAt);
  }
}
