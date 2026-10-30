package com.editographer.asset.infrastructure;

import com.editographer.asset.domain.Asset;
import com.editographer.asset.domain.AssetId;
import com.editographer.asset.domain.AssetRepository;
import com.editographer.project.domain.ProjectId;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Component;

/** JPA implementation of the asset port. */
@Component
final class AssetRepositoryAdapter implements AssetRepository {

  private final JpaAssetRepository jpa;

  AssetRepositoryAdapter(JpaAssetRepository jpa) {
    this.jpa = jpa;
  }

  @Override
  public Asset save(Asset asset) {
    return AssetMapper.toDomain(jpa.save(AssetMapper.toEntity(asset)));
  }

  @Override
  public List<Asset> findByProject(ProjectId projectId) {
    return jpa.findByProjectIdOrderByCreatedAtAsc(projectId.value()).stream()
        .map(AssetMapper::toDomain)
        .toList();
  }

  @Override
  public Optional<Asset> findById(AssetId id) {
    return jpa.findById(id.value()).map(AssetMapper::toDomain);
  }

  @Override
  public void deleteById(AssetId id) {
    jpa.deleteById(id.value());
  }
}
