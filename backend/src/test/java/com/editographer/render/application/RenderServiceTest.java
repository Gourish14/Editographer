package com.editographer.render.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.editographer.asset.domain.Asset;
import com.editographer.asset.domain.AssetRepository;
import com.editographer.asset.domain.AssetType;
import com.editographer.common.error.ApiException;
import com.editographer.common.error.ErrorCode;
import com.editographer.events.domain.EventPublisher;
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
import com.editographer.render.domain.RenderStatus;
import com.editographer.render.domain.StylePresetRepository;
import com.editographer.storage.domain.MediaPath;
import com.editographer.worker.domain.WorkerClient;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class RenderServiceTest {

  private static final Instant NOW = Instant.parse("2026-10-30T10:00:00Z");
  private static final RenderSettings SETTINGS =
      new RenderSettings("9:16", "4K", 30, "velocity", "fast", 30, "slow-mo", false, 7L);

  private final RenderRepository renders = mock(RenderRepository.class);
  private final ProjectRepository projects = mock(ProjectRepository.class);
  private final AssetRepository assets = mock(AssetRepository.class);
  private final StylePresetRepository styles = mock(StylePresetRepository.class);
  private final JobQueue queue = mock(JobQueue.class);
  private final WorkerClient worker = mock(WorkerClient.class);
  private final EventPublisher events = mock(EventPublisher.class);
  private final RenderService service =
      new RenderService(
          renders,
          projects,
          assets,
          styles,
          queue,
          worker,
          events,
          Clock.fixed(NOW, ZoneOffset.UTC));
  private final ProjectId projectId = ProjectId.newId();

  @BeforeEach
  void aProjectReadyToRender() {
    when(projects.existsById(projectId)).thenReturn(true);
    when(styles.existsById("velocity")).thenReturn(true);
    when(renders.save(any())).thenAnswer(call -> call.getArgument(0));
    when(assets.findByProject(projectId))
        .thenReturn(List.of(asset(AssetType.MUSIC), asset(AssetType.VIDEO)));
  }

  private Asset asset(AssetType type) {
    return Asset.uploaded(projectId, type, "a.mp4", 1L, NOW);
  }

  private Render stored(Render render) {
    when(renders.findById(render.id())).thenReturn(Optional.of(render));
    return render;
  }

  private Render queuedRender() {
    return stored(Render.queued(projectId, SETTINGS, NOW));
  }

  private static void assertFailsWith(Runnable action, ErrorCode expected) {
    assertThatThrownBy(action::run)
        .isInstanceOfSatisfying(
            ApiException.class, error -> assertThat(error.errorCode()).isEqualTo(expected));
  }

  @Test
  void startingARenderSavesItAndQueuesARenderJob() {
    Render render = service.startRender(projectId, SETTINGS);

    assertThat(render.state().status()).isEqualTo(RenderStatus.QUEUED);
    assertThat(render.settings()).isEqualTo(SETTINGS);
    verify(queue).enqueue(JobKind.RENDER, render.id().value());
  }

  @Test
  void anUnknownProjectCannotRender() {
    ProjectId unknown = ProjectId.newId();

    assertFailsWith(() -> service.startRender(unknown, SETTINGS), ErrorCode.PROJECT_NOT_FOUND);
  }

  @Test
  void anUnknownStyleIsRefused() {
    when(styles.existsById("velocity")).thenReturn(false);

    assertFailsWith(() -> service.startRender(projectId, SETTINGS), ErrorCode.VALIDATION_FAILED);
  }

  @Test
  void aProjectWithoutMusicIsRefused() {
    when(assets.findByProject(projectId)).thenReturn(List.of(asset(AssetType.VIDEO)));

    assertFailsWith(() -> service.startRender(projectId, SETTINGS), ErrorCode.VALIDATION_FAILED);
    verify(queue, never()).enqueue(any(), any());
  }

  @Test
  void anLrfDoesNotCountAsAClip() {
    Asset proxy = Asset.uploaded(projectId, AssetType.VIDEO, "PANO.LRF", 1L, NOW);
    when(assets.findByProject(projectId)).thenReturn(List.of(asset(AssetType.MUSIC), proxy));

    assertFailsWith(() -> service.startRender(projectId, SETTINGS), ErrorCode.VALIDATION_FAILED);
  }

  @Test
  void aProjectWithOnlyMusicIsRefused() {
    when(assets.findByProject(projectId)).thenReturn(List.of(asset(AssetType.MUSIC)));

    assertFailsWith(() -> service.startRender(projectId, SETTINGS), ErrorCode.VALIDATION_FAILED);
  }

  @Test
  void regeneratingMakesANewRenderWithTheSameSettingsAndANewSeed() {
    Render original = queuedRender();

    Render version = service.regenerate(original.id());

    assertThat(version.id()).isNotEqualTo(original.id());
    assertThat(version.settings().seed()).isNotEqualTo(SETTINGS.seed());
    assertThat(version.settings().withSeed(SETTINGS.seed())).isEqualTo(SETTINGS);
    verify(queue).enqueue(JobKind.RENDER, version.id().value());
  }

  @Test
  void anUnknownRenderIsNotFound() {
    RenderId unknown = RenderId.newId();
    when(renders.findById(unknown)).thenReturn(Optional.empty());

    assertFailsWith(() -> service.getRender(unknown), ErrorCode.RENDER_NOT_FOUND);
  }

  @Test
  void cancellingAQueuedRenderDropsItsJobWithoutCallingTheWorker() {
    Render render = queuedRender();
    Job job = new Job(UUID.randomUUID(), JobKind.RENDER, render.id().value(), JobStatus.QUEUED, 0);
    when(queue.findUnfinishedFor(render.id().value())).thenReturn(Optional.of(job));

    Render cancelled = service.cancel(render.id());

    assertThat(cancelled.state().status()).isEqualTo(RenderStatus.CANCELLED);
    verify(queue).finish(job.id(), JobStatus.FAILED);
    verify(worker, never()).cancel(any());
    verify(events).publish(eq(render.id().value()), argThat(event -> event.last()));
  }

  @Test
  void cancellingARunningRenderAsksTheWorkerToStop() {
    Render render = queuedRender();
    Job job = new Job(UUID.randomUUID(), JobKind.RENDER, render.id().value(), JobStatus.RUNNING, 1);
    when(queue.findUnfinishedFor(render.id().value())).thenReturn(Optional.of(job));

    service.cancel(render.id());

    verify(worker).cancel(job.id());
    verify(queue, never()).finish(any(), any());
  }

  @Test
  void anUnreachableWorkerStillLetsARenderBeCancelled() {
    Render render = queuedRender();
    Job job = new Job(UUID.randomUUID(), JobKind.RENDER, render.id().value(), JobStatus.RUNNING, 1);
    when(queue.findUnfinishedFor(render.id().value())).thenReturn(Optional.of(job));
    doThrow(new ApiException(ErrorCode.WORKER_UNAVAILABLE, "down")).when(worker).cancel(job.id());

    assertThat(service.cancel(render.id()).state().status()).isEqualTo(RenderStatus.CANCELLED);
    verify(queue).finish(job.id(), JobStatus.FAILED);
  }

  @Test
  void aFinishedRenderCannotBeCancelled() {
    Render render = stored(queuedRender().failed("boom", NOW));

    assertFailsWith(() -> service.cancel(render.id()), ErrorCode.RENDER_ALREADY_FINISHED);
  }

  @Test
  void previewAndFinalAreNotReadyBeforeTheWorkerReportsThem() {
    Render render = queuedRender();

    assertFailsWith(() -> service.previewOf(render.id()), ErrorCode.RENDER_NOT_READY);
    assertFailsWith(() -> service.outputOf(render.id()), ErrorCode.RENDER_NOT_READY);
  }

  @Test
  void previewAndFinalPathsComeFromTheRender() {
    MediaPath preview = new MediaPath("renders/r/preview.mp4");
    MediaPath output = new MediaPath("renders/r/final.mp4");
    Render render = stored(queuedRender().withPreview(preview).done(output, "{}", NOW));

    assertThat(service.previewOf(render.id())).isEqualTo(preview);
    assertThat(service.outputOf(render.id())).isEqualTo(output);
  }

  @Test
  void aLateListenerLearnsARenderIsDone() {
    Render render = stored(queuedRender().done(new MediaPath("renders/r/final.mp4"), "{}", NOW));

    assertThat(service.currentEvent(render.id()).orElseThrow().name()).isEqualTo("done");
  }

  @Test
  void aLateListenerLearnsARenderFailed() {
    Render render = stored(queuedRender().failed("boom", NOW));

    assertThat(service.currentEvent(render.id()).orElseThrow().name()).isEqualTo("failed");
  }

  @Test
  void aLateListenerGetsTheLatestProgress() {
    Render render = stored(queuedRender().progressed("COMPOSING", 40));

    assertThat(service.currentEvent(render.id()).orElseThrow().name()).isEqualTo("progress");
  }

  @Test
  void aListenerToAQueuedRenderHearsNothingYet() {
    Render render = queuedRender();

    assertThat(service.currentEvent(render.id())).isEmpty();
  }

  @Test
  void listComesFromTheRepository() {
    when(renders.findByProject(projectId)).thenReturn(List.of());

    assertThat(service.listRenders(projectId)).isEmpty();
  }
}
