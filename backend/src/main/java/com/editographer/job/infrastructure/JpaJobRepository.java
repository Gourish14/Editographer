package com.editographer.job.infrastructure;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

interface JpaJobRepository extends JpaRepository<JpaJobEntity, UUID> {

  @Query(
      "select j from JpaJobEntity j where j.status = :status"
          + " and (j.notBefore is null or j.notBefore <= :now)"
          + " order by j.priority asc, j.createdAt asc limit 1")
  Optional<JpaJobEntity> findNextDue(
      @Param("status") String status, @Param("now") java.time.Instant now);

  List<JpaJobEntity> findByStatus(String status);

  Optional<JpaJobEntity> findFirstByRefIdAndStatusIn(UUID refId, List<String> statuses);
}
