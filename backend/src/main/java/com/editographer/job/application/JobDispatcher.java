package com.editographer.job.application;

import com.editographer.common.error.ApiException;
import com.editographer.common.logging.LoggingConstants;
import com.editographer.job.domain.Job;
import com.editographer.job.domain.JobKind;
import com.editographer.job.domain.JobQueue;
import com.editographer.job.domain.JobStatus;
import com.editographer.worker.domain.WorkerClient;
import com.editographer.worker.domain.WorkerStatus;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * Sends the next job whenever the worker is idle. Spec:
 * specs/02-architecture.md#job-queue-replaces-rabbitmq
 */
@Component
public class JobDispatcher {

  private static final Logger LOG = LoggerFactory.getLogger(JobDispatcher.class);

  private final JobQueue queue;
  private final WorkerClient worker;
  private final Map<JobKind, JobSender> senders;
  private final JobFailureHandler failures;
  private final Clock clock;
  private final Duration grace;
  private final int maxAttempts;

  public JobDispatcher(
      JobQueue queue,
      WorkerClient worker,
      List<JobSender> senders,
      JobFailureHandler failures,
      Clock clock,
      @Value("${app.job-stuck-grace-ms:30000}") long graceMs,
      @Value("${app.job-max-attempts:3}") int maxAttempts) {
    this.queue = queue;
    this.worker = worker;
    this.failures = failures;
    this.clock = clock;
    this.grace = Duration.ofMillis(graceMs);
    this.maxAttempts = maxAttempts;
    this.senders = senders.stream().collect(Collectors.toMap(JobSender::kind, Function.identity()));
  }

  @Scheduled(fixedDelayString = "${app.dispatch-interval-ms}")
  public void dispatchNext() {
    worker.status().ifPresent(this::recoverStuckJobs);
    if (worker.isIdle()) {
      queue.nextQueued().ifPresent(this::dispatch);
    }
  }

  /**
   * A job that the backend thinks is running but the worker is not running (idle, restarted, or on
   * another job) is requeued, or failed once it used up its attempts. The grace period covers the
   * moment between sending a job and the worker reporting busy. BUG-008.
   */
  private void recoverStuckJobs(WorkerStatus status) {
    Instant now = clock.instant();
    for (Job job : queue.findRunning()) {
      boolean old = job.startedAt() != null && !job.startedAt().plus(grace).isAfter(now);
      boolean workerHasIt = status.busy() && job.id().toString().equals(status.currentJobId());
      if (old && !workerHasIt) {
        recover(job);
      }
    }
  }

  private void recover(Job job) {
    if (job.attempts() >= maxAttempts) {
      String error = "The worker lost this job " + job.attempts() + " times";
      queue.finish(job.id(), JobStatus.FAILED);
      failures.jobAbandoned(job, error);
      LOG.atError()
          .addKeyValue(LoggingConstants.EVENT, "job.abandoned")
          .addKeyValue(LoggingConstants.JOB_ID, job.id().toString())
          .log(error);
    } else {
      queue.requeue(job.id());
      LOG.atWarn()
          .addKeyValue(LoggingConstants.EVENT, "job.requeued_stuck")
          .addKeyValue(LoggingConstants.JOB_ID, job.id().toString())
          .log("The worker is not running this job, it goes back in the queue");
    }
  }

  private void dispatch(Job job) {
    MDC.put(LoggingConstants.REQUEST_ID, UUID.randomUUID().toString());
    MDC.put(LoggingConstants.JOB_ID, job.id().toString());
    try {
      JobSender sender = senders.get(job.kind());
      if (sender == null) {
        LOG.atDebug().log("No sender registered for this job kind yet");
        return;
      }
      queue.markRunning(job.id());
      if (sender.send(job)) {
        LOG.atInfo().addKeyValue(LoggingConstants.EVENT, "job.sent").log("Job sent to worker");
      } else {
        queue.finish(job.id(), JobStatus.FAILED);
        LOG.atWarn()
            .addKeyValue(LoggingConstants.EVENT, "job.orphaned")
            .log("Job dropped because what it refers to was deleted");
      }
    } catch (ApiException exception) {
      queue.requeue(job.id());
      LOG.atWarn()
          .addKeyValue(LoggingConstants.EVENT, "job.send_failed")
          .addKeyValue(LoggingConstants.ERROR_CODE, exception.errorCode().name())
          .log("Could not send job, it stays queued");
    } finally {
      MDC.remove(LoggingConstants.JOB_ID);
      MDC.remove(LoggingConstants.REQUEST_ID);
    }
  }
}
