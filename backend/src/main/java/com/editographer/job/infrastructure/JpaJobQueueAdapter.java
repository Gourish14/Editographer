package com.editographer.job.infrastructure;

import com.editographer.job.domain.JobKind;
import com.editographer.job.domain.JobQueue;
import java.time.Clock;
import java.util.UUID;
import org.springframework.stereotype.Component;

/** Keeps the job queue in the database. ADR-002. */
@Component
final class JpaJobQueueAdapter implements JobQueue {

  private final JpaJobRepository jobs;
  private final Clock clock;

  JpaJobQueueAdapter(JpaJobRepository jobs, Clock clock) {
    this.jobs = jobs;
    this.clock = clock;
  }

  @Override
  public void enqueue(JobKind kind, UUID refId) {
    jobs.save(
        new JpaJobEntity(UUID.randomUUID(), kind.name(), refId, kind.priority(), clock.instant()));
  }
}
