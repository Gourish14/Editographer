package com.editographer.job.application;

import com.editographer.job.domain.JobQueue;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/**
 * Re-queues jobs that were running when the backend stopped. Spec:
 * specs/02-architecture.md#job-queue-replaces-rabbitmq
 */
@Component
public class JobRecovery {

  private final JobQueue queue;

  public JobRecovery(JobQueue queue) {
    this.queue = queue;
  }

  @EventListener(ApplicationReadyEvent.class)
  @Transactional
  public void requeueInterruptedJobs() {
    queue.requeueAllRunning();
  }
}
