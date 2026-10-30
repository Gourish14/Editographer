package com.editographer.asset.infrastructure;

import com.editographer.asset.domain.AnalysisStatus;
import com.editographer.asset.domain.Asset;
import com.editographer.asset.domain.AssetId;
import com.editographer.asset.domain.AssetType;
import com.editographer.project.domain.ProjectId;
import com.editographer.storage.domain.MediaPath;

/** Converts between the domain model and its JPA row. */
final class AssetMapper {

  private AssetMapper() {}

  static JpaAssetEntity toEntity(Asset asset) {
    return new JpaAssetEntity(
        asset.id().value(),
        asset.projectId().value(),
        asset.type().name(),
        asset.filename(),
        asset.path().value(),
        asset.sizeBytes(),
        asset.analysisStatus().name(),
        asset.fileHash(),
        asset.durationSec(),
        asset.width(),
        asset.height(),
        asset.fps(),
        asset.cameraMode(),
        asset.logProfile(),
        asset.analysisPath(),
        asset.createdAt());
  }

  static Asset toDomain(JpaAssetEntity entity) {
    return new Asset(
        new AssetId(entity.getId()),
        new ProjectId(entity.getProjectId()),
        AssetType.valueOf(entity.getType()),
        entity.getFilename(),
        new MediaPath(entity.getPath()),
        entity.getSizeBytes(),
        AnalysisStatus.valueOf(entity.getAnalysisStatus()),
        entity.getFileHash(),
        entity.getDurationSec(),
        entity.getWidth(),
        entity.getHeight(),
        entity.getFps(),
        entity.getCameraMode(),
        entity.getLogProfile(),
        entity.getAnalysisPath(),
        entity.getCreatedAt());
  }
}
