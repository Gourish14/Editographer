package com.editographer.project.api.dto;

import com.editographer.asset.api.dto.AssetResponse;
import com.editographer.render.api.dto.RenderResponse;
import java.util.List;

/** A project with its assets and renders, as returned by GET /api/projects/{id}. */
public record ProjectDetailResponse(
    ProjectResponse project, List<AssetResponse> assets, List<RenderResponse> renders) {

  public ProjectDetailResponse {
    assets = List.copyOf(assets);
    renders = List.copyOf(renders);
  }
}
