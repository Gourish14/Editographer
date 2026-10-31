package com.editographer.job.domain;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

/** A unit of worker work. Spec: specs/07-api-and-data.md#job-flow */
public record Job(
    UUID id, JobKind kind, UUID refId, JobStatus status, int attempts, Instant startedAt) {

  public Job(UUID id, JobKind kind, UUID refId, JobStatus status, int attempts) {
    this(id, kind, refId, status, attempts, null);
  }

  public Job {
    Objects.requireNonNull(id, "id");
    Objects.requireNonNull(kind, "kind");
    Objects.requireNonNull(refId, "refId");
    Objects.requireNonNull(status, "status");
  }
}
