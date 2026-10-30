package com.editographer.asset.api.dto;

import com.editographer.asset.domain.Asset;
import java.time.Instant;
import java.util.UUID;

/** An asset as seen by API clients. */
public record AssetResponse(
    UUID id,
    UUID projectId,
    String type,
    String filename,
    long sizeBytes,
    String analysisStatus,
    Double durationSec,
    Integer width,
    Integer height,
    Double fps,
    String cameraMode,
    String logProfile,
    Instant createdAt) {

  public static AssetResponse from(Asset asset) {
    return new AssetResponse(
        asset.id().value(),
        asset.projectId().value(),
        asset.type().name(),
        asset.filename(),
        asset.sizeBytes(),
        asset.analysisStatus().name(),
        asset.durationSec(),
        asset.width(),
        asset.height(),
        asset.fps(),
        asset.cameraMode(),
        asset.logProfile(),
        asset.createdAt());
  }
}
