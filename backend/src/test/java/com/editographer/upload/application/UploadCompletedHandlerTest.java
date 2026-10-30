package com.editographer.upload.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.inOrder;
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
import com.editographer.job.domain.JobKind;
import com.editographer.job.domain.JobQueue;
import com.editographer.project.domain.ProjectId;
import com.editographer.project.domain.ProjectRepository;
import com.editographer.storage.domain.MediaWriter;
import com.editographer.upload.domain.UploadMetadata;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Base64;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.mockito.InOrder;

class UploadCompletedHandlerTest {

  private static final Instant NOW = Instant.parse("2026-10-30T10:00:00Z");
  private static final UUID PROJECT = UUID.fromString("00000000-0000-0000-0000-000000000001");

  private final ProjectRepository projects = mock(ProjectRepository.class);
  private final AssetRepository assets = mock(AssetRepository.class);
  private final MediaWriter mediaWriter = mock(MediaWriter.class);
  private final JobQueue jobQueue = mock(JobQueue.class);
  private final UploadCompletedHandler handler =
      new UploadCompletedHandler(
          projects, assets, mediaWriter, jobQueue, Clock.fixed(NOW, ZoneOffset.UTC));

  private static String header(String filename) {
    Base64.Encoder encoder = Base64.getEncoder();
    return "projectId "
        + encoder.encodeToString(PROJECT.toString().getBytes(StandardCharsets.UTF_8))
        + ",filename "
        + encoder.encodeToString(filename.getBytes(StandardCharsets.UTF_8));
  }

  private static CompletedUpload upload(String filename) {
    return new CompletedUpload(
        "/api/uploads/x", new UploadMetadata(PROJECT, filename), Path.of("incoming"), 42L);
  }

  private static void assertFailsWith(Runnable action, ErrorCode expected) {
    assertThatThrownBy(action::run)
        .isInstanceOfSatisfying(
            ApiException.class, error -> assertThat(error.errorCode()).isEqualTo(expected));
  }

  @Test
  void acceptsAnUploadForAnExistingProject() {
    when(projects.existsById(new ProjectId(PROJECT))).thenReturn(true);

    assertThatCode(() -> handler.checkCanStart(header("clip.mp4"))).doesNotThrowAnyException();
  }

  @Test
  void refusesMissingMetadataBeforeAnyBytesAreSent() {
    assertFailsWith(() -> handler.checkCanStart(null), ErrorCode.UPLOAD_FAILED);
  }

  @Test
  void refusesAnUnsupportedFileBeforeAnyBytesAreSent() {
    when(projects.existsById(any())).thenReturn(true);

    assertFailsWith(() -> handler.checkCanStart(header("virus.exe")), ErrorCode.ASSET_UNSUPPORTED);
  }

  @Test
  void refusesAnUnknownProjectBeforeAnyBytesAreSent() {
    when(projects.existsById(any())).thenReturn(false);

    assertFailsWith(() -> handler.checkCanStart(header("clip.mp4")), ErrorCode.PROJECT_NOT_FOUND);
  }

  @Test
  void completionCreatesAPendingAssetQueuesAnalysisAndStoresTheFile() throws IOException {
    Asset asset = handler.complete(upload("clip.mp4"));

    assertThat(asset.type()).isEqualTo(AssetType.VIDEO);
    assertThat(asset.analysisStatus()).isEqualTo(AnalysisStatus.PENDING);
    assertThat(asset.sizeBytes()).isEqualTo(42L);
    assertThat(asset.createdAt()).isEqualTo(NOW);
    verify(assets).save(asset);
    verify(jobQueue).enqueue(JobKind.ANALYZE, asset.id().value());
    verify(mediaWriter).moveIn(Path.of("incoming"), asset.path());
  }

  @Test
  void anLrfIsStoredAsReadyWithNoAnalysisJob() throws IOException {
    handler.complete(upload("PANO_001.LRF"));

    verify(assets).save(argThat(asset -> asset.analysisStatus() == AnalysisStatus.DONE));
    verify(jobQueue, never()).enqueue(any(), any());
  }

  @Test
  void theFileMovesOnlyAfterTheRowsAreWritten() throws IOException {
    handler.complete(upload("clip.mp4"));

    InOrder order = inOrder(assets, jobQueue, mediaWriter);
    order.verify(assets).save(any());
    order.verify(jobQueue).enqueue(eq(JobKind.ANALYZE), any());
    order.verify(mediaWriter).moveIn(any(), any());
  }

  @Test
  void aDatabaseFailureLeavesTheFileUnmoved() throws IOException {
    doThrow(new IllegalStateException("db down")).when(jobQueue).enqueue(any(), any());

    assertThatThrownBy(() -> handler.complete(upload("clip.mp4")))
        .isInstanceOf(IllegalStateException.class);

    verify(mediaWriter, never()).moveIn(any(), any());
  }
}
