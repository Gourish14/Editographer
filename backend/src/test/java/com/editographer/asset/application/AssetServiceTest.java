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
import com.editographer.asset.domain.AssetId;
import com.editographer.asset.domain.AssetRepository;
import com.editographer.asset.domain.AssetType;
import com.editographer.common.error.ApiException;
import com.editographer.common.error.ErrorCode;
import com.editographer.project.domain.ProjectId;
import com.editographer.project.domain.ProjectRepository;
import com.editographer.storage.domain.MediaLocator;
import com.editographer.storage.domain.MediaPath;
import com.editographer.storage.domain.MediaWriter;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class AssetServiceTest {

  private static final Instant NOW = Instant.parse("2026-10-30T10:00:00Z");
  private static final String HASH = "abc123";

  private final AssetRepository assets = mock(AssetRepository.class);
  private final ProjectRepository projects = mock(ProjectRepository.class);
  private final MediaLocator locator = mock(MediaLocator.class);
  private final MediaWriter writer = mock(MediaWriter.class);
  private final AssetService service = new AssetService(assets, projects, locator, writer);
  private final ProjectId projectId = ProjectId.newId();

  private Asset uploaded() {
    return Asset.uploaded(projectId, AssetType.VIDEO, "clip.mp4", 1L, NOW);
  }

  private Asset analyzed() {
    Asset a = uploaded();
    return new Asset(
        a.id(),
        a.projectId(),
        a.type(),
        a.filename(),
        a.path(),
        a.sizeBytes(),
        AnalysisStatus.DONE,
        HASH,
        1.0,
        1920,
        1080,
        30.0,
        "FLAT",
        null,
        "cache/" + HASH + "/analysis.json",
        a.createdAt());
  }

  private void assertFailsWith(Runnable action, ErrorCode expected) {
    assertThatThrownBy(action::run)
        .isInstanceOfSatisfying(
            ApiException.class, error -> assertThat(error.errorCode()).isEqualTo(expected));
  }

  @Test
  void listReturnsTheProjectsAssets() {
    List<Asset> stored = List.of(uploaded());
    when(projects.existsById(projectId)).thenReturn(true);
    when(assets.findByProject(projectId)).thenReturn(stored);

    assertThat(service.listAssets(projectId)).isEqualTo(stored);
  }

  @Test
  void listFailsForAnUnknownProject() {
    when(projects.existsById(projectId)).thenReturn(false);

    assertFailsWith(() -> service.listAssets(projectId), ErrorCode.PROJECT_NOT_FOUND);
  }

  @Test
  void thumbnailComesFromTheAnalysisCache() {
    Asset asset = analyzed();
    MediaPath expected = new MediaPath("cache/" + HASH + "/thumbnail.jpg");
    when(assets.findById(asset.id())).thenReturn(Optional.of(asset));
    when(locator.exists(expected)).thenReturn(true);

    assertThat(service.thumbnailOf(asset.id())).isEqualTo(expected);
  }

  @Test
  void thumbnailIsNotFoundBeforeAnalysis() {
    Asset asset = uploaded();
    when(assets.findById(asset.id())).thenReturn(Optional.of(asset));

    assertFailsWith(() -> service.thumbnailOf(asset.id()), ErrorCode.ASSET_NOT_FOUND);
  }

  @Test
  void thumbnailIsNotFoundWhenTheFileIsMissing() {
    Asset asset = analyzed();
    when(assets.findById(asset.id())).thenReturn(Optional.of(asset));
    when(locator.exists(any())).thenReturn(false);

    assertFailsWith(() -> service.thumbnailOf(asset.id()), ErrorCode.ASSET_NOT_FOUND);
  }

  @Test
  void deleteRemovesTheRowAndTheFile() throws IOException {
    Asset asset = uploaded();
    when(assets.findById(asset.id())).thenReturn(Optional.of(asset));

    service.deleteAsset(asset.id());

    verify(assets).deleteById(asset.id());
    verify(writer).delete(asset.path());
  }

  @Test
  void deleteFailsForAnUnknownAssetAndRemovesNothing() throws IOException {
    AssetId id = AssetId.newId();
    when(assets.findById(id)).thenReturn(Optional.empty());

    assertFailsWith(() -> service.deleteAsset(id), ErrorCode.ASSET_NOT_FOUND);
    verify(assets, never()).deleteById(any());
    verify(writer, never()).delete(any());
  }

  @Test
  void aFileThatCannotBeDeletedFailsTheOperation() throws IOException {
    Asset asset = uploaded();
    when(assets.findById(asset.id())).thenReturn(Optional.of(asset));
    doThrow(new IOException("locked")).when(writer).delete(asset.path());

    assertThatThrownBy(() -> service.deleteAsset(asset.id()))
        .isInstanceOf(UncheckedIOException.class);
  }
}
