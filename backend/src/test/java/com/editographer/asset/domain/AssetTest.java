package com.editographer.asset.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.editographer.project.domain.ProjectId;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class AssetTest {

  private static final Instant NOW = Instant.parse("2026-10-30T10:00:00Z");
  private final ProjectId projectId = ProjectId.newId();

  @Test
  void uploadedAssetIsPendingAndStoredUnderItsProjectWithItsOwnId() {
    Asset asset = Asset.uploaded(projectId, AssetType.VIDEO, "My Clip.MP4", 42L, NOW);

    assertThat(asset.analysisStatus()).isEqualTo(AnalysisStatus.PENDING);
    assertThat(asset.filename()).isEqualTo("My Clip.MP4");
    assertThat(asset.path().value())
        .isEqualTo("uploads/" + projectId.value() + "/" + asset.id().value() + ".mp4");
  }

  @Test
  void projectFolderHoldsTheProjectsUploads() {
    assertThat(Asset.projectFolder(projectId).value()).isEqualTo("uploads/" + projectId.value());
  }

  @Test
  void rejectsABlankFilename() {
    assertThatThrownBy(() -> Asset.uploaded(projectId, AssetType.VIDEO, " ", 1L, NOW))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void rejectsANegativeSize() {
    assertThatThrownBy(() -> Asset.uploaded(projectId, AssetType.VIDEO, "a.mp4", -1L, NOW))
        .isInstanceOf(IllegalArgumentException.class);
  }
}
