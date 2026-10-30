package com.editographer.project.infrastructure;

import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

interface JpaProjectRepository extends JpaRepository<JpaProjectEntity, UUID> {

  List<JpaProjectEntity> findAllByOrderByCreatedAtDesc();
}
