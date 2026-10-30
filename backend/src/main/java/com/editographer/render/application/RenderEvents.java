package com.editographer.render.application;

import com.editographer.events.domain.StreamEvent;
import com.editographer.render.domain.Render;
import com.editographer.render.domain.RenderStatus;
import java.util.Map;
import java.util.Optional;

/**
 * The live events of a render. Spec: specs/07-api-and-data.md (progress, preview-ready, done,
 * failed)
 */
final class RenderEvents {

  private static final String PROGRESS = "progress";
  private static final String PREVIEW_READY = "preview-ready";
  private static final String DONE = "done";
  private static final String FAILED = "failed";

  private RenderEvents() {}

  static StreamEvent progress(String stage, int percent, String message) {
    return new StreamEvent(
        PROGRESS,
        Map.of("stage", stage, "percent", percent, "message", message == null ? "" : message),
        false);
  }

  static StreamEvent previewReady() {
    return new StreamEvent(PREVIEW_READY, Map.of(), false);
  }

  static StreamEvent done() {
    return new StreamEvent(DONE, Map.of(), true);
  }

  static StreamEvent failed(String error) {
    return new StreamEvent(FAILED, Map.of("error", error == null ? "" : error), true);
  }

  /** What someone connecting now needs to be told first. */
  static Optional<StreamEvent> currentState(Render render) {
    RenderStatus status = render.state().status();
    if (status == RenderStatus.DONE) {
      return Optional.of(done());
    }
    if (status.isFinished()) {
      return Optional.of(failed(render.state().error()));
    }
    if (render.state().stage() != null) {
      return Optional.of(progress(render.state().stage(), render.state().progress(), null));
    }
    return Optional.empty();
  }
}
