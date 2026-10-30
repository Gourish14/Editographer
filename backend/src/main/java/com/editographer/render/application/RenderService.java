package com.editographer.render.application;

import com.editographer.asset.domain.Asset;
import com.editographer.asset.domain.AssetRepository;
import com.editographer.asset.domain.AssetType;
import com.editographer.common.error.ApiException;
import com.editographer.common.error.ErrorCode;
import com.editographer.events.domain.EventPublisher;
import com.editographer.events.domain.StreamEvent;
import com.editographer.job.domain.Job;
import com.editographer.job.domain.JobKind;
import com.editographer.job.domain.JobQueue;
import com.editographer.job.domain.JobStatus;
import com.editographer.project.domain.ProjectId;
import com.editographer.project.domain.ProjectRepository;
import com.editographer.render.domain.Render;
import com.editographer.render.domain.RenderId;
import com.editographer.render.domain.RenderRepository;
import com.editographer.render.domain.RenderSettings;
import com.editographer.render.domain.StylePresetRepository;
import com.editographer.storage.domain.MediaPath;
import com.editographer.worker.domain.WorkerClient;
import java.time.Clock;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.ThreadLocalRandom;
import java.util.function.Function;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Render use cases. Spec: specs/07-api-and-data.md#job-flow */
@Service
public class RenderService {

  private final RenderRepository renders;
  private final ProjectRepository projects;
  private final AssetRepository assets;
  private final StylePresetRepository styles;
  private final JobQueue queue;
  private final WorkerClient worker;
  private final EventPublisher events;
  private final Clock clock;

  public RenderService(
      RenderRepository renders,
      ProjectRepository projects,
      AssetRepository assets,
      StylePresetRepository styles,
      JobQueue queue,
      WorkerClient worker,
      EventPublisher events,
      Clock clock) {
    this.renders = renders;
    this.projects = projects;
    this.assets = assets;
    this.styles = styles;
    this.queue = queue;
    this.worker = worker;
    this.events = events;
    this.clock = clock;
  }

  /** Starts a render once the project has what an edit needs. */
  @Transactional
  public Render startRender(ProjectId projectId, RenderSettings settings) {
    if (!projects.existsById(projectId)) {
      throw new ApiException(
          ErrorCode.PROJECT_NOT_FOUND, "Project " + projectId.value() + " not found");
    }
    if (!styles.existsById(settings.style())) {
      throw new ApiException(ErrorCode.VALIDATION_FAILED, "Unknown style: " + settings.style());
    }
    requireInputs(projectId);
    return enqueue(Render.queued(projectId, settings, clock.instant()));
  }

  /** "Make another version": same settings and inputs with a new seed. */
  @Transactional
  public Render regenerate(RenderId id) {
    Render original = find(id);
    RenderSettings settings = original.settings().withSeed(randomSeed());
    return enqueue(Render.queued(original.projectId(), settings, clock.instant()));
  }

  @Transactional(readOnly = true)
  public Render getRender(RenderId id) {
    return find(id);
  }

  @Transactional(readOnly = true)
  public List<Render> listRenders(ProjectId projectId) {
    return renders.findByProject(projectId);
  }

  /** Stops a queued or running render. The worker stops after its current stage. */
  @Transactional
  public Render cancel(RenderId id) {
    Render render = find(id);
    if (render.isFinished()) {
      throw new ApiException(
          ErrorCode.RENDER_ALREADY_FINISHED, "Render " + id.value() + " has already finished");
    }
    queue.findUnfinishedFor(id.value()).ifPresent(this::stop);
    Render cancelled = renders.save(render.cancelled(clock.instant()));
    events.publish(id.value(), RenderEvents.failed(ErrorCode.RENDER_CANCELLED.name()));
    return cancelled;
  }

  @Transactional(readOnly = true)
  public MediaPath previewOf(RenderId id) {
    return fileOf(id, render -> render.state().previewPath(), "preview");
  }

  @Transactional(readOnly = true)
  public MediaPath outputOf(RenderId id) {
    return fileOf(id, render -> render.state().outputPath(), "final video");
  }

  /** The event that tells someone connecting now where the render stands. */
  @Transactional(readOnly = true)
  public Optional<StreamEvent> currentEvent(RenderId id) {
    return RenderEvents.currentState(find(id));
  }

  public static long randomSeed() {
    return ThreadLocalRandom.current().nextLong(Long.MAX_VALUE);
  }

  private Render enqueue(Render render) {
    Render saved = renders.save(render);
    queue.enqueue(JobKind.RENDER, saved.id().value());
    return saved;
  }

  private void requireInputs(ProjectId projectId) {
    List<Asset> inputs = assets.findByProject(projectId);
    boolean hasMusic = inputs.stream().anyMatch(asset -> asset.type() == AssetType.MUSIC);
    boolean hasFootage = inputs.stream().anyMatch(asset -> asset.type() != AssetType.MUSIC);
    if (!hasMusic || !hasFootage) {
      throw new ApiException(
          ErrorCode.VALIDATION_FAILED, "A render needs at least one music track and one clip");
    }
  }

  private void stop(Job job) {
    if (job.status() == JobStatus.QUEUED) {
      queue.finish(job.id(), JobStatus.FAILED);
      return;
    }
    try {
      worker.cancel(job.id());
    } catch (ApiException exception) {
      queue.finish(job.id(), JobStatus.FAILED);
    }
  }

  private Render find(RenderId id) {
    return renders
        .findById(id)
        .orElseThrow(
            () ->
                new ApiException(
                    ErrorCode.RENDER_NOT_FOUND, "Render " + id.value() + " not found"));
  }

  private MediaPath fileOf(RenderId id, Function<Render, MediaPath> file, String description) {
    MediaPath path = file.apply(find(id));
    if (path == null) {
      throw new ApiException(
          ErrorCode.RENDER_NOT_READY, "The " + description + " is not ready yet");
    }
    return path;
  }
}
