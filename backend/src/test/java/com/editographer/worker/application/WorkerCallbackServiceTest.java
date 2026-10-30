package com.editographer.worker.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentCaptor.forClass;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.editographer.asset.domain.AnalysisResult;
import com.editographer.asset.domain.AnalysisStatus;
import com.editographer.asset.domain.Asset;
import com.editographer.asset.domain.AssetId;
import com.editographer.asset.domain.AssetRepository;
import com.editographer.asset.domain.AssetType;
import com.editographer.common.error.ApiException;
import com.editographer.common.error.ErrorCode;
import com.editographer.job.domain.Job;
import com.editographer.job.domain.JobKind;
import com.editographer.job.domain.JobQueue;
import com.editographer.job.domain.JobStatus;
import com.editographer.project.domain.ProjectId;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class WorkerCallbackServiceTest {

  private final AssetRepository assets = mock(AssetRepository.class);
  private final JobQueue queue = mock(JobQueue.class);
  private final WorkerCallbackService service = new WorkerCallbackService(assets, queue);
  private final Asset asset =
      Asset.uploaded(ProjectId.newId(), AssetType.VIDEO, "a.mp4", 1L, Instant.EPOCH);

  private Asset savedAsset() {
    ArgumentCaptor<Asset> saved = forClass(Asset.class);
    verify(assets).save(saved.capture());
    return saved.getValue();
  }

  @Test
  void analyzedAssetStoresTheResultAndBecomesDone() {
    when(assets.findById(asset.id())).thenReturn(Optional.of(asset));
    AnalysisResult result =
        new AnalysisResult("cache/h/analysis.json", "h", "FLAT", "DLOGM", 12.5, 3840, 2160, 29.97);

    service.assetAnalyzed(asset.id(), result);

    Asset saved = savedAsset();
    assertThat(saved.analysisStatus()).isEqualTo(AnalysisStatus.DONE);
    assertThat(saved.analysisPath()).isEqualTo("cache/h/analysis.json");
    assertThat(saved.fileHash()).isEqualTo("h");
    assertThat(saved.cameraMode()).isEqualTo("FLAT");
    assertThat(saved.logProfile()).isEqualTo("DLOGM");
    assertThat(saved.durationSec()).isEqualTo(12.5);
    assertThat(saved.width()).isEqualTo(3840);
    assertThat(saved.height()).isEqualTo(2160);
    assertThat(saved.fps()).isEqualTo(29.97);
  }

  @Test
  void analyzedCallbackForAnUnknownAssetFails() {
    AssetId unknown = AssetId.newId();
    when(assets.findById(unknown)).thenReturn(Optional.empty());
    AnalysisResult result = new AnalysisResult("x", null, null, null, null, null, null, null);

    assertThatThrownBy(() -> service.assetAnalyzed(unknown, result))
        .isInstanceOfSatisfying(
            ApiException.class,
            error -> assertThat(error.errorCode()).isEqualTo(ErrorCode.ASSET_NOT_FOUND));
  }

  @Test
  void aFailedAnalysisMarksItsAssetFailed() {
    Job job = new Job(UUID.randomUUID(), JobKind.ANALYZE, asset.id().value(), JobStatus.RUNNING, 1);
    when(queue.findById(job.id())).thenReturn(Optional.of(job));
    when(assets.findById(asset.id())).thenReturn(Optional.of(asset));

    service.jobCompleted(job.id(), JobStatus.FAILED);

    verify(queue).finish(job.id(), JobStatus.FAILED);
    assertThat(savedAsset().analysisStatus()).isEqualTo(AnalysisStatus.FAILED);
  }

  @Test
  void aFinishedAnalysisLeavesTheAssetAlone() {
    Job job = new Job(UUID.randomUUID(), JobKind.ANALYZE, asset.id().value(), JobStatus.RUNNING, 1);
    when(queue.findById(job.id())).thenReturn(Optional.of(job));

    service.jobCompleted(job.id(), JobStatus.DONE);

    verify(queue).finish(job.id(), JobStatus.DONE);
    verify(assets, never()).save(any());
  }

  @Test
  void completingAnUnknownJobFails() {
    UUID unknown = UUID.randomUUID();
    when(queue.findById(unknown)).thenReturn(Optional.empty());

    assertThatThrownBy(() -> service.jobCompleted(unknown, JobStatus.DONE))
        .isInstanceOfSatisfying(
            ApiException.class,
            error -> assertThat(error.errorCode()).isEqualTo(ErrorCode.JOB_NOT_FOUND));
  }
}
