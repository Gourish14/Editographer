package com.editographer.job.domain;

import java.util.UUID;

/** Port for the durable job queue. Spec: specs/02-architecture.md#job-queue-replaces-rabbitmq */
public interface JobQueue {

  /** Queues work on the asset or render with the given id. */
  void enqueue(JobKind kind, UUID refId);
}
