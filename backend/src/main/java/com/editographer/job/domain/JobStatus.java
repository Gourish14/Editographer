package com.editographer.job.domain;

/** Lifecycle of a job. Spec: specs/02-architecture.md#job-queue-replaces-rabbitmq */
public enum JobStatus {
  QUEUED,
  RUNNING,
  DONE,
  FAILED
}
