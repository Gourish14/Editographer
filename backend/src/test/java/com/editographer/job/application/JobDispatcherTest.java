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
  private final Job job =
      new Job(UUID.randomUUID(), JobKind.ANALYZE, UUID.randomUUID(), JobStatus.QUEUED, 0);

  private JobDispatcher dispatcher() {
    when(sender.kind()).thenReturn(JobKind.ANALYZE);
    return new JobDispatcher(queue, worker, List.of(sender));
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
}
