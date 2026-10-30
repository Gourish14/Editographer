package com.editographer.job.infrastructure;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

interface JpaJobRepository extends JpaRepository<JpaJobEntity, UUID> {

  Optional<JpaJobEntity> findFirstByStatusOrderByPriorityAscCreatedAtAsc(String status);

  List<JpaJobEntity> findByStatus(String status);
}
