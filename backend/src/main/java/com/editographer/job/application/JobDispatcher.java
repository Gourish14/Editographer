package com.editographer.job.application;

import com.editographer.common.error.ApiException;
import com.editographer.common.logging.LoggingConstants;
import com.editographer.job.domain.Job;
import com.editographer.job.domain.JobKind;
import com.editographer.job.domain.JobQueue;
import com.editographer.job.domain.JobStatus;
import com.editographer.worker.domain.WorkerClient;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
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

  public JobDispatcher(JobQueue queue, WorkerClient worker, List<JobSender> senders) {
    this.queue = queue;
    this.worker = worker;
    this.senders = senders.stream().collect(Collectors.toMap(JobSender::kind, Function.identity()));
  }

  @Scheduled(fixedDelayString = "${app.dispatch-interval-ms}")
  public void dispatchNext() {
    if (worker.isIdle()) {
      queue.nextQueued().ifPresent(this::dispatch);
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
