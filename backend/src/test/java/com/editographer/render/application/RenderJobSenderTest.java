package com.editographer.render.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentCaptor.forClass;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.editographer.asset.domain.AnalysisResult;
import com.editographer.asset.domain.AnalysisStatus;
import com.editographer.asset.domain.Asset;
import com.editographer.asset.domain.AssetRepository;
import com.editographer.asset.domain.AssetType;
import com.editographer.job.domain.Job;
import com.editographer.job.domain.JobKind;
import com.editographer.job.domain.JobStatus;
import com.editographer.project.domain.ProjectId;
import com.editographer.render.domain.Render;
import com.editographer.render.domain.RenderRepository;
import com.editographer.render.domain.RenderSettings;
import com.editographer.worker.domain.RenderJobRequest;
import com.editographer.worker.domain.WorkerClient;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class RenderJobSenderTest {

  private final RenderRepository renders = mock(RenderRepository.class);
  private final AssetRepository assets = mock(AssetRepository.class);
  private final WorkerClient worker = mock(WorkerClient.class);
  private final RenderJobSender sender = new RenderJobSender(renders, assets, worker);
  private final ProjectId projectId = ProjectId.newId();
  private final RenderSettings settings =
      new RenderSettings("9:16", "4K", 30, "auto", "fast", null, null, false, 1L);
  private final Render render = Render.queued(projectId, settings, Instant.EPOCH);
  private final Job job =
      new Job(UUID.randomUUID(), JobKind.RENDER, render.id().value(), JobStatus.RUNNING, 1);

  private Asset asset(String name) {
    return Asset.uploaded(projectId, AssetType.VIDEO, name, 1L, Instant.EPOCH);
  }

  @Test
  void sendsTheRenderWithOnlyItsAnalyzedAssets() {
    Asset ready =
        asset("ready.mp4")
            .withAnalysis(
                new AnalysisResult("cache/h/analysis.json", "h", "FLAT", null, 5.0, 1, 1, 30.0));
    Asset failed = asset("failed.mp4").withAnalysisStatus(AnalysisStatus.FAILED);
    when(renders.findById(render.id())).thenReturn(Optional.of(render));
    when(assets.findByProject(projectId)).thenReturn(List.of(ready, failed));

    assertThat(sender.send(job)).isTrue();

    ArgumentCaptor<RenderJobRequest> sent = forClass(RenderJobRequest.class);
    verify(worker).submitRender(sent.capture());
    assertThat(sent.getValue().settings()).isEqualTo(settings);
    assertThat(sent.getValue().assets())
        .extracting(RenderJobRequest.AssetInput::id)
        .containsExactly(ready.id().value());
  }

  @Test
  void reportsFalseForARenderThatWasDeleted() {
    when(renders.findById(render.id())).thenReturn(Optional.empty());

    assertThat(sender.send(job)).isFalse();
    verify(worker, never()).submitRender(any());
  }

  @Test
  void reportsFalseForARenderThatWasCancelled() {
    when(renders.findById(render.id())).thenReturn(Optional.of(render.cancelled(Instant.EPOCH)));

    assertThat(sender.send(job)).isFalse();
    verify(worker, never()).submitRender(any());
  }
}
