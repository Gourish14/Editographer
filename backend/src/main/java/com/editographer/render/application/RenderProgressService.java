package com.editographer.render.application;

import com.editographer.events.domain.EventPublisher;
import com.editographer.render.domain.Render;
import com.editographer.render.domain.RenderId;
import com.editographer.render.domain.RenderRepository;
import com.editographer.storage.domain.MediaPath;
import java.time.Clock;
import java.util.Optional;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Applies worker reports to a render and pushes them to the browser. A report for a render that has
 * finished, such as one cancelled mid-stage, is ignored. Spec: specs/07-api-and-data.md#job-flow
 * steps 5 to 7
 */
@Service
public class RenderProgressService {

  private final RenderRepository renders;
  private final EventPublisher events;
  private final Clock clock;

  public RenderProgressService(RenderRepository renders, EventPublisher events, Clock clock) {
    this.renders = renders;
    this.events = events;
    this.clock = clock;
  }

  @Transactional
  public void progress(RenderId id, String stage, int percent, String message) {
    active(id)
        .ifPresent(
            render -> {
              renders.save(render.progressed(stage, percent));
              events.publish(id.value(), RenderEvents.progress(stage, percent, message));
            });
  }

  @Transactional
  public void previewReady(RenderId id, MediaPath path) {
    active(id)
        .ifPresent(
            render -> {
              renders.save(render.withPreview(path));
              events.publish(id.value(), RenderEvents.previewReady());
            });
  }

  @Transactional
  public void completed(RenderId id, MediaPath output, String plan) {
    active(id)
        .ifPresent(
            render -> {
              renders.save(render.done(output, plan, clock.instant()));
              events.publish(id.value(), RenderEvents.done());
            });
  }

  @Transactional
  public void failed(RenderId id, String error) {
    active(id)
        .ifPresent(
            render -> {
              renders.save(render.failed(error, clock.instant()));
              events.publish(id.value(), RenderEvents.failed(error));
            });
  }

  private Optional<Render> active(RenderId id) {
    return renders.findById(id).filter(render -> !render.isFinished());
  }
}
