package com.editographer.project.api.dto;

import com.editographer.asset.api.dto.AssetResponse;
import java.util.List;

/** A project with its assets, as returned by GET /api/projects/{id}. Renders join in T-107. */
public record ProjectDetailResponse(ProjectResponse project, List<AssetResponse> assets) {

  public ProjectDetailResponse {
    assets = List.copyOf(assets);
  }
}
