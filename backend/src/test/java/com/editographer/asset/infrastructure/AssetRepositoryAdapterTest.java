package com.editographer.asset.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;

import com.editographer.asset.domain.Asset;
import com.editographer.asset.domain.AssetId;
import com.editographer.asset.domain.AssetRepository;
import com.editographer.asset.domain.AssetType;
import com.editographer.project.domain.Project;
import com.editographer.project.domain.ProjectId;
import com.editographer.project.domain.ProjectRepository;
import java.time.Instant;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.data.jpa.test.autoconfigure.DataJpaTest;
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.FilterType;
import org.springframework.context.annotation.Import;
import org.springframework.stereotype.Component;

@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@Import(AssetRepositoryAdapterTest.Adapters.class)
class AssetRepositoryAdapterTest {

  private static final Instant OLDER = Instant.parse("2026-10-29T10:00:00Z");
  private static final Instant NEWER = Instant.parse("2026-10-30T10:00:00Z");

  @Autowired private AssetRepository assets;
  @Autowired private ProjectRepository projects;

  private ProjectId projectId;

  @TestConfiguration
  @ComponentScan(
      basePackages = {
        "com.editographer.asset.infrastructure",
        "com.editographer.project.infrastructure"
      },
      useDefaultFilters = false,
      includeFilters =
          @ComponentScan.Filter(type = FilterType.ANNOTATION, classes = Component.class))
  static class Adapters {}

  @BeforeEach
  void createProject() {
    projectId = projects.save(Project.create("p", NEWER)).id();
  }

  @Test
  void savedAssetCanBeReadBackUnchanged() {
    Asset asset = assets.save(Asset.uploaded(projectId, AssetType.MUSIC, "song.mp3", 9L, NEWER));

    assertThat(assets.findById(asset.id())).contains(asset);
  }

  @Test
  void findByProjectReturnsUploadOrderAndOnlyThatProject() {
    Asset first = assets.save(Asset.uploaded(projectId, AssetType.VIDEO, "a.mp4", 1L, OLDER));
    Asset second = assets.save(Asset.uploaded(projectId, AssetType.VIDEO, "b.mp4", 1L, NEWER));
    ProjectId other = projects.save(Project.create("other", NEWER)).id();
    assets.save(Asset.uploaded(other, AssetType.VIDEO, "c.mp4", 1L, NEWER));

    assertThat(assets.findByProject(projectId)).containsExactly(first, second);
  }

  @Test
  void findByIdIsEmptyForAnUnknownAsset() {
    assertThat(assets.findById(AssetId.newId())).isEmpty();
  }

  @Test
  void deleteByIdRemovesTheAsset() {
    Asset asset = assets.save(Asset.uploaded(projectId, AssetType.VIDEO, "a.mp4", 1L, NEWER));

    assets.deleteById(asset.id());

    assertThat(assets.findById(asset.id())).isEmpty();
  }
}
