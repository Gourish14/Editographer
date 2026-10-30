package com.editographer.job.domain;

/**
 * Kinds of worker job. A lower priority number runs first. Spec:
 * specs/02-architecture.md#job-queue-replaces-rabbitmq
 */
public enum JobKind {
  ANALYZE(1),
  RENDER(2);

  private final int priority;

  JobKind(int priority) {
    this.priority = priority;
  }

  public int priority() {
    return priority;
  }
}
