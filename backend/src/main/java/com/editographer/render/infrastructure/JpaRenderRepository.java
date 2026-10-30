package com.editographer.render.infrastructure;

import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

interface JpaRenderRepository extends JpaRepository<JpaRenderEntity, UUID> {

  List<JpaRenderEntity> findByProjectIdOrderByCreatedAtDesc(UUID projectId);
}
