package com.editographer.worker.domain;

import com.editographer.asset.domain.Asset;
import com.editographer.render.domain.RenderSettings;
import java.util.List;
import java.util.UUID;

/** Body of POST /jobs/render. Paths are relative to the media folder. */
public record RenderJobRequest(
    UUID jobId, UUID renderId, UUID projectId, RenderSettings settings, List<AssetInput> assets) {

  public RenderJobRequest {
    assets = List.copyOf(assets);
  }

  /** One analyzed asset the worker may use. */
  public record AssetInput(
      UUID id,
      String type,
      String path,
      String analysisPath,
      String cameraMode,
      String logProfile,
      Double durationSec,
      Integer width,
      Integer height,
      Double fps) {

    public static AssetInput from(Asset asset) {
      return new AssetInput(
          asset.id().value(),
          asset.type().name(),
          asset.path().value(),
          asset.analysisPath(),
          asset.cameraMode(),
          asset.logProfile(),
          asset.durationSec(),
          asset.width(),
          asset.height(),
          asset.fps());
    }
  }
}
