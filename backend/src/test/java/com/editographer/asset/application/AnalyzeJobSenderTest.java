package com.editographer.asset.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.editographer.asset.domain.AnalysisStatus;
import com.editographer.asset.domain.Asset;
import com.editographer.asset.domain.AssetRepository;
import com.editographer.asset.domain.AssetType;
import com.editographer.common.error.ApiException;
import com.editographer.common.error.ErrorCode;
import com.editographer.job.domain.Job;
import com.editographer.job.domain.JobKind;
import com.editographer.job.domain.JobStatus;
import com.editographer.project.domain.ProjectId;
import com.editographer.worker.domain.AnalyzeJobRequest;
import com.editographer.worker.domain.WorkerClient;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class AnalyzeJobSenderTest {

  private final AssetRepository assets = mock(AssetRepository.class);
  private final WorkerClient worker = mock(WorkerClient.class);
  private final AnalyzeJobSender sender = new AnalyzeJobSender(assets, worker);
  private final Asset asset =
      Asset.uploaded(ProjectId.newId(), AssetType.VIDEO, "a.mp4", 1L, Instant.EPOCH);
  private final Job job =
      new Job(UUID.randomUUID(), JobKind.ANALYZE, asset.id().value(), JobStatus.RUNNING, 1);

  @Test
  void sendsTheAssetAndMarksItRunning() {
    when(assets.findById(asset.id())).thenReturn(Optional.of(asset));

    assertThat(sender.send(job)).isTrue();

    verify(worker)
        .submitAnalyze(
            new AnalyzeJobRequest(job.id(), asset.id().value(), asset.path().value(), "VIDEO"));
    verify(assets).save(asset.withAnalysisStatus(AnalysisStatus.RUNNING));
  }

  @Test
  void reportsFalseWhenTheAssetWasDeleted() {
    when(assets.findById(asset.id())).thenReturn(Optional.empty());

    assertThat(sender.send(job)).isFalse();

    verify(worker, never()).submitAnalyze(any());
  }

  @Test
  void anUnreachableWorkerLeavesTheAssetPending() {
    when(assets.findById(asset.id())).thenReturn(Optional.of(asset));
    doThrow(new ApiException(ErrorCode.WORKER_UNAVAILABLE, "down"))
        .when(worker)
        .submitAnalyze(any());

    assertThatThrownBy(() -> sender.send(job)).isInstanceOf(ApiException.class);

    verify(assets, never()).save(any());
  }
}
