package com.editographer.job.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.editographer.common.error.ApiException;
import com.editographer.common.error.ErrorCode;
import com.editographer.common.logging.LoggingConstants;
import com.editographer.job.domain.Job;
import com.editographer.job.domain.JobKind;
import com.editographer.job.domain.JobQueue;
import com.editographer.job.domain.JobStatus;
import com.editographer.worker.domain.WorkerClient;
import com.editographer.worker.domain.WorkerStatus;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;

class JobDispatcherTest {

  private final JobQueue queue = mock(JobQueue.class);
  private final WorkerClient worker = mock(WorkerClient.class);
  private final JobSender sender = mock(JobSender.class);
  private final JobFailureHandler failures = mock(JobFailureHandler.class);
  private final Instant now = Instant.parse("2026-01-01T00:10:00Z");
  private final Clock clock = Clock.fixed(now, ZoneOffset.UTC);
  private final Job job =
      new Job(UUID.randomUUID(), JobKind.ANALYZE, UUID.randomUUID(), JobStatus.QUEUED, 0);

  private JobDispatcher dispatcher() {
    when(sender.kind()).thenReturn(JobKind.ANALYZE);
    return new JobDispatcher(queue, worker, List.of(sender), failures, clock, 30_000, 3);
  }

  @Test
  void doesNothingWhileTheWorkerIsBusyOrUnreachable() {
    when(worker.isIdle()).thenReturn(false);

    dispatcher().dispatchNext();

    verify(queue, never()).nextQueued();
  }

  @Test
  void doesNothingWhenTheQueueIsEmpty() {
    when(worker.isIdle()).thenReturn(true);
    when(queue.nextQueued()).thenReturn(Optional.empty());

    dispatcher().dispatchNext();

    verify(sender, never()).send(any());
  }

  @Test
  void sendsTheNextJobAndMarksItRunning() {
    when(worker.isIdle()).thenReturn(true);
    when(queue.nextQueued()).thenReturn(Optional.of(job));
    when(sender.send(job)).thenReturn(true);

    dispatcher().dispatchNext();

    verify(queue).markRunning(job.id());
    verify(queue, never()).requeue(any());
  }

  @Test
  void anUnreachableWorkerPutsTheJobBackInTheQueue() {
    when(worker.isIdle()).thenReturn(true);
    when(queue.nextQueued()).thenReturn(Optional.of(job));
    when(sender.send(job)).thenThrow(new ApiException(ErrorCode.WORKER_UNAVAILABLE, "down"));

    dispatcher().dispatchNext();

    verify(queue).requeue(job.id());
  }

  @Test
  void aJobWhoseAssetWasDeletedFails() {
    when(worker.isIdle()).thenReturn(true);
    when(queue.nextQueued()).thenReturn(Optional.of(job));
    when(sender.send(job)).thenReturn(false);

    dispatcher().dispatchNext();

    verify(queue).finish(job.id(), JobStatus.FAILED);
  }

  @Test
  void aKindWithoutASenderStaysQueued() {
    Job render = new Job(UUID.randomUUID(), JobKind.RENDER, UUID.randomUUID(), JobStatus.QUEUED, 0);
    when(worker.isIdle()).thenReturn(true);
    when(queue.nextQueued()).thenReturn(Optional.of(render));

    dispatcher().dispatchNext();

    verify(queue, never()).markRunning(any());
  }

  @Test
  void theJobIdIsInTheLoggingContextDuringSendAndClearedAfter() {
    AtomicReference<String> seen = new AtomicReference<>();
    when(worker.isIdle()).thenReturn(true);
    when(queue.nextQueued()).thenReturn(Optional.of(job));
    when(sender.send(job))
        .thenAnswer(
            call -> {
              seen.set(MDC.get(LoggingConstants.JOB_ID));
              return true;
            });

    dispatcher().dispatchNext();

    assertThat(seen).hasValue(job.id().toString());
    assertThat(MDC.get(LoggingConstants.JOB_ID)).isNull();
    assertThat(MDC.get(LoggingConstants.REQUEST_ID)).isNull();
  }

  private Job running(int attempts, long startedSecondsAgo) {
    return new Job(
        UUID.randomUUID(),
        JobKind.RENDER,
        UUID.randomUUID(),
        JobStatus.RUNNING,
        attempts,
        now.minusSeconds(startedSecondsAgo));
  }

  private void workerSays(boolean busy, String current) {
    when(worker.status()).thenReturn(Optional.of(new WorkerStatus(busy, current, null)));
  }

  @Test
  void recoveryARunningJobTheIdleWorkerForgotIsRequeued() {
    Job stuck = running(1, 120);
    when(queue.findRunning()).thenReturn(List.of(stuck));
    workerSays(false, null);

    dispatcher().dispatchNext();

    verify(queue).requeue(stuck.id());
    verify(failures, never()).jobAbandoned(any(), any());
  }

  @Test
  void recoveryAJobTheWorkerStillRunsIsLeftAlone() {
    Job live = running(1, 120);
    when(queue.findRunning()).thenReturn(List.of(live));
    workerSays(true, live.id().toString());

    dispatcher().dispatchNext();

    verify(queue, never()).requeue(any());
  }

  @Test
  void recoveryAWorkerOnAnotherJobMeansThisOneIsLost() {
    Job stuck = running(1, 120);
    when(queue.findRunning()).thenReturn(List.of(stuck));
    workerSays(true, UUID.randomUUID().toString());

    dispatcher().dispatchNext();

    verify(queue).requeue(stuck.id());
  }

  @Test
  void recoveryAJobJustSentGetsAGracePeriod() {
    Job fresh = running(1, 5);
    when(queue.findRunning()).thenReturn(List.of(fresh));
    workerSays(false, null);

    dispatcher().dispatchNext();

    verify(queue, never()).requeue(any());
  }

  @Test
  void recoveryAJobOutOfAttemptsFailsAndItsRenderIsTold() {
    Job tired = running(3, 120);
    when(queue.findRunning()).thenReturn(List.of(tired));
    workerSays(false, null);

    dispatcher().dispatchNext();

    verify(queue).finish(tired.id(), JobStatus.FAILED);
    verify(failures).jobAbandoned(org.mockito.ArgumentMatchers.eq(tired), any());
    verify(queue, never()).requeue(any());
  }
}
