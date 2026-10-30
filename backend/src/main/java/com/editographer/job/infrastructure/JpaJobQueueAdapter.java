package com.editographer.job.infrastructure;

import com.editographer.job.domain.Job;
import com.editographer.job.domain.JobKind;
import com.editographer.job.domain.JobQueue;
import com.editographer.job.domain.JobStatus;
import java.time.Clock;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
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
  public void enqueue(JobKind kind, UUID refId, Instant notBefore) {
    jobs.save(
        new JpaJobEntity(
            UUID.randomUUID(), kind.name(), refId, kind.priority(), clock.instant(), notBefore));
  }

  @Override
  public Optional<Job> nextQueued() {
    return jobs.findNextDue(JobStatus.QUEUED.name(), clock.instant())
        .map(JpaJobQueueAdapter::toDomain);
  }

  @Override
  public Optional<Job> findById(UUID id) {
    return jobs.findById(id).map(JpaJobQueueAdapter::toDomain);
  }

  @Override
  public Optional<Job> findUnfinishedFor(UUID refId) {
    List<String> unfinished = List.of(JobStatus.QUEUED.name(), JobStatus.RUNNING.name());
    return jobs.findFirstByRefIdAndStatusIn(refId, unfinished).map(JpaJobQueueAdapter::toDomain);
  }

  @Override
  public void markRunning(UUID id) {
    jobs.findById(id)
        .ifPresent(
            job -> {
              job.start(JobStatus.RUNNING.name(), clock.instant());
              jobs.save(job);
            });
  }

  @Override
  public void requeue(UUID id) {
    finish(id, JobStatus.QUEUED);
  }

  @Override
  public void requeueAllRunning() {
    List<JpaJobEntity> running = jobs.findByStatus(JobStatus.RUNNING.name());
    running.forEach(job -> job.changeStatus(JobStatus.QUEUED.name()));
    jobs.saveAll(running);
  }

  @Override
  public void finish(UUID id, JobStatus status) {
    jobs.findById(id)
        .ifPresent(
            job -> {
              job.changeStatus(status.name());
              jobs.save(job);
            });
  }

  private static Job toDomain(JpaJobEntity row) {
    return new Job(
        row.getId(),
        JobKind.valueOf(row.getKind()),
        row.getRefId(),
        JobStatus.valueOf(row.getStatus()),
        row.getAttempts());
  }
}
