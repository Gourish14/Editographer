package com.editographer.asset.domain;

import com.editographer.project.domain.ProjectId;
import java.util.List;
import java.util.Optional;

/** Port for storing assets. */
public interface AssetRepository {

  Asset save(Asset asset);

  /** A project's assets, oldest first, in upload order. */
  List<Asset> findByProject(ProjectId projectId);

  Optional<Asset> findById(AssetId id);

  void deleteById(AssetId id);
}
