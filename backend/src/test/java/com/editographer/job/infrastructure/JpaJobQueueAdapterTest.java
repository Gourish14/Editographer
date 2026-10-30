package com.editographer.job.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;

import com.editographer.common.config.ClockConfig;
import com.editographer.job.domain.JobKind;
import com.editographer.job.domain.JobQueue;
import java.util.UUID;
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

  @Test
  void analyzeJobIsQueuedAheadOfRenderPriority() {
    UUID refId = UUID.randomUUID();

    queue.enqueue(JobKind.ANALYZE, refId);

    JpaJobEntity job =
        rows.findAll().stream()
            .filter(row -> refId.equals(row.getRefId()))
            .findFirst()
            .orElseThrow();
    assertThat(job.getKind()).isEqualTo("ANALYZE");
    assertThat(job.getStatus()).isEqualTo("QUEUED");
    assertThat(job.getAttempts()).isZero();
    assertThat(job.getStartedAt()).isNull();
    assertThat(job.getPriority()).isLessThan(JobKind.RENDER.priority());
  }
}
