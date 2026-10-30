package com.editographer.asset.infrastructure;

import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

interface JpaAssetRepository extends JpaRepository<JpaAssetEntity, UUID> {

  List<JpaAssetEntity> findByProjectIdOrderByCreatedAtAsc(UUID projectId);
}
