package com.editographer.render.api.dto;

import com.editographer.render.domain.Render;
import com.editographer.render.domain.RenderSettings;
import com.editographer.render.domain.RenderState;
import com.fasterxml.jackson.annotation.JsonRawValue;
import java.time.Instant;
import java.util.UUID;

/** A render as seen by API clients. Log and plan are stored JSON, passed through unchanged. */
public record RenderResponse(
    UUID id,
    UUID projectId,
    RenderSettings settings,
    String status,
    String stage,
    int progress,
    @JsonRawValue String log,
    @JsonRawValue String editPlan,
    boolean previewReady,
    boolean finalReady,
    String error,
    Instant createdAt,
    Instant finishedAt) {

  public static RenderResponse from(Render render) {
    RenderState state = render.state();
    return new RenderResponse(
        render.id().value(),
        render.projectId().value(),
        render.settings(),
        state.status().name(),
        state.stage(),
        state.progress(),
        state.log(),
        state.editPlan(),
        state.previewPath() != null,
        state.outputPath() != null,
        state.error(),
        render.createdAt(),
        state.finishedAt());
  }
}
