package com.editographer.job.infrastructure;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

/** JPA row for a queued job. Never leaves the infrastructure layer. */
@Entity
@Table(name = "job")
class JpaJobEntity {

  static final String STATUS_QUEUED = "QUEUED";

  @Id private UUID id;

  @Column(nullable = false)
  private String kind;

  @Column(name = "ref_id", nullable = false)
  private UUID refId;

  @Column(nullable = false)
  private int priority;

  @Column(nullable = false)
  private String status;

  @Column(nullable = false)
  private int attempts;

  @Column(name = "created_at", nullable = false)
  private Instant createdAt;

  @Column(name = "not_before")
  private Instant notBefore;

  @Column(name = "started_at")
  private Instant startedAt;

  protected JpaJobEntity() {}

  JpaJobEntity(
      UUID id, String kind, UUID refId, int priority, Instant createdAt, Instant notBefore) {
    this.id = id;
    this.kind = kind;
    this.refId = refId;
    this.priority = priority;
    this.status = STATUS_QUEUED;
    this.createdAt = createdAt;
    this.notBefore = notBefore;
  }

  void start(String runningStatus, Instant now) {
    status = runningStatus;
    startedAt = now;
    attempts++;
  }

  void changeStatus(String newStatus) {
    status = newStatus;
  }

  UUID getId() {
    return id;
  }

  String getKind() {
    return kind;
  }

  UUID getRefId() {
    return refId;
  }

  int getPriority() {
    return priority;
  }

  String getStatus() {
    return status;
  }

  int getAttempts() {
    return attempts;
  }

  Instant getStartedAt() {
    return startedAt;
  }
}
