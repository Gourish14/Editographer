package com.editographer.job.infrastructure;

import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

interface JpaJobRepository extends JpaRepository<JpaJobEntity, UUID> {}
