package com.editographer.job.domain;

import java.util.Optional;
import java.util.UUID;

/** Port for the durable job queue. Spec: specs/02-architecture.md#job-queue-replaces-rabbitmq */
public interface JobQueue {

  /** Queues work on the asset or render with the given id. */
  void enqueue(JobKind kind, UUID refId);

  /** The queued job that should run next: lowest priority number, then oldest. */
  Optional<Job> nextQueued();

  Optional<Job> findById(UUID id);

  /** Records that the job was handed to the worker. */
  void markRunning(UUID id);

  /** Puts a job back in the queue, for example when the worker could not be reached. */
  void requeue(UUID id);

  /** Moves every running job back to the queue. Used after a backend restart. */
  void requeueAllRunning();

  void finish(UUID id, JobStatus status);
}
