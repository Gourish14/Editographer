package com.editographer.job.domain;

import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

/** Port for the durable job queue. Spec: specs/02-architecture.md#job-queue-replaces-rabbitmq */
public interface JobQueue {

  /** Queues work on the asset or render with the given id. */
  default void enqueue(JobKind kind, UUID refId) {
    enqueue(kind, refId, null);
  }

  /**
   * Queues work that must not start before notBefore. A null notBefore means as soon as possible.
   */
  void enqueue(JobKind kind, UUID refId, Instant notBefore);

  /**
   * The queued job that should run next: lowest priority number, then oldest. Jobs whose start time
   * has not come yet are skipped.
   */
  Optional<Job> nextQueued();

  Optional<Job> findById(UUID id);

  /** The queued or running job for an asset or render, if there is one. */
  Optional<Job> findUnfinishedFor(UUID refId);

  /** Every job handed to the worker and not yet reported as finished. */
  java.util.List<Job> findRunning();

  /** Records that the job was handed to the worker. */
  void markRunning(UUID id);

  /** Puts a job back in the queue, for example when the worker could not be reached. */
  void requeue(UUID id);

  /** Moves every running job back to the queue. Used after a backend restart. */
  void requeueAllRunning();

  void finish(UUID id, JobStatus status);
}
