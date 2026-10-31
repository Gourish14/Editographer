package com.editographer.job.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;

import com.editographer.common.config.ClockConfig;
import com.editographer.job.domain.Job;
import com.editographer.job.domain.JobKind;
import com.editographer.job.domain.JobQueue;
import com.editographer.job.domain.JobStatus;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.data.jpa.test.autoconfigure.DataJpaTest;
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase;
import org.springframework.context.annotation.Import;

@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@Import({JpaJobQueueAdapter.class, ClockConfig.class})
class JpaJobQueueAdapterTest {

  @Autowired private JobQueue queue;
  @Autowired private JpaJobRepository rows;

  @BeforeEach
  void startEmpty() {
    rows.deleteAll();
  }

  private Job next() {
    return queue.nextQueued().orElseThrow();
  }

  private JobQueue queueWithClockAt(String instant) {
    return new JpaJobQueueAdapter(rows, Clock.fixed(Instant.parse(instant), ZoneOffset.UTC));
  }

  @Test
  void aNewJobIsQueuedWithNoAttempts() {
    UUID refId = UUID.randomUUID();

    queue.enqueue(JobKind.ANALYZE, refId);

    Job job = next();
    assertThat(job.kind()).isEqualTo(JobKind.ANALYZE);
    assertThat(job.refId()).isEqualTo(refId);
    assertThat(job.status()).isEqualTo(JobStatus.QUEUED);
    assertThat(job.attempts()).isZero();
  }

  @Test
  void analysisRunsBeforeRenderEvenWhenQueuedLater() {
    queueWithClockAt("2026-10-30T10:00:00Z").enqueue(JobKind.RENDER, UUID.randomUUID());
    queueWithClockAt("2026-10-30T11:00:00Z").enqueue(JobKind.ANALYZE, UUID.randomUUID());

    assertThat(next().kind()).isEqualTo(JobKind.ANALYZE);
  }

  @Test
  void jobsOfTheSamePriorityRunOldestFirst() {
    UUID older = UUID.randomUUID();
    queueWithClockAt("2026-10-30T11:00:00Z").enqueue(JobKind.ANALYZE, UUID.randomUUID());
    queueWithClockAt("2026-10-30T10:00:00Z").enqueue(JobKind.ANALYZE, older);

    assertThat(next().refId()).isEqualTo(older);
  }

  @Test
  void aRunningJobLeavesTheQueueAndCountsAnAttempt() {
    queue.enqueue(JobKind.ANALYZE, UUID.randomUUID());
    UUID id = next().id();

    queue.markRunning(id);

    assertThat(queue.nextQueued()).isEmpty();
    Job job = queue.findById(id).orElseThrow();
    assertThat(job.status()).isEqualTo(JobStatus.RUNNING);
    assertThat(job.attempts()).isEqualTo(1);
  }

  @Test
  void restartResetsRunningJobsToQueuedAndLeavesFinishedOnesAlone() {
    queue.enqueue(JobKind.ANALYZE, UUID.randomUUID());
    UUID interrupted = next().id();
    queue.markRunning(interrupted);
    queue.enqueue(JobKind.ANALYZE, UUID.randomUUID());
    UUID finished = next().id();
    queue.finish(finished, JobStatus.DONE);

    queue.requeueAllRunning();

    assertThat(queue.findById(interrupted).orElseThrow().status()).isEqualTo(JobStatus.QUEUED);
    assertThat(queue.findById(finished).orElseThrow().status()).isEqualTo(JobStatus.DONE);
  }

  @Test
  void requeuePutsAJobBack() {
    queue.enqueue(JobKind.ANALYZE, UUID.randomUUID());
    UUID id = next().id();
    queue.markRunning(id);

    queue.requeue(id);

    assertThat(next().id()).isEqualTo(id);
  }

  @Test
  void aJobWithAStartTimeWaitsUntilThatTime() {
    UUID refId = UUID.randomUUID();
    queueWithClockAt("2026-10-30T10:00:00Z")
        .enqueue(JobKind.RENDER, refId, Instant.parse("2026-10-30T22:00:00Z"));

    assertThat(queueWithClockAt("2026-10-30T21:59:59Z").nextQueued()).isEmpty();
    assertThat(queueWithClockAt("2026-10-30T22:00:00Z").nextQueued())
        .hasValueSatisfying(job -> assertThat(job.refId()).isEqualTo(refId));
  }

  @Test
  void aWaitingJobDoesNotBlockLaterReadyWork() {
    queueWithClockAt("2026-10-30T10:00:00Z")
        .enqueue(JobKind.ANALYZE, UUID.randomUUID(), Instant.parse("2026-10-30T22:00:00Z"));
    UUID ready = UUID.randomUUID();
    queueWithClockAt("2026-10-30T11:00:00Z").enqueue(JobKind.RENDER, ready);

    assertThat(queueWithClockAt("2026-10-30T12:00:00Z").nextQueued())
        .hasValueSatisfying(job -> assertThat(job.refId()).isEqualTo(ready));
  }

  @Test
  void findByIdIsEmptyForAnUnknownJob() {
    assertThat(queue.findById(UUID.randomUUID())).isEmpty();
  }
}
