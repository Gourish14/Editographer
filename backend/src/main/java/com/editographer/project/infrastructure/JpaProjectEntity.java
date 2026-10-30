package com.editographer.project.infrastructure;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

/** JPA row for a project. Never leaves the infrastructure layer. */
@Entity
@Table(name = "project")
class JpaProjectEntity {

  @Id private UUID id;

  @Column(nullable = false)
  private String name;

  @Column(name = "created_at", nullable = false)
  private Instant createdAt;

  protected JpaProjectEntity() {}

  JpaProjectEntity(UUID id, String name, Instant createdAt) {
    this.id = id;
    this.name = name;
    this.createdAt = createdAt;
  }

  UUID getId() {
    return id;
  }

  String getName() {
    return name;
  }

  Instant getCreatedAt() {
    return createdAt;
  }
}
