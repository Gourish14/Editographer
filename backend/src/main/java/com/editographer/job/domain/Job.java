package com.editographer.job.domain;

import java.util.Objects;
import java.util.UUID;

/** A unit of worker work. Spec: specs/07-api-and-data.md#job-flow */
public record Job(UUID id, JobKind kind, UUID refId, JobStatus status, int attempts) {

  public Job {
    Objects.requireNonNull(id, "id");
    Objects.requireNonNull(kind, "kind");
    Objects.requireNonNull(refId, "refId");
    Objects.requireNonNull(status, "status");
  }
}
