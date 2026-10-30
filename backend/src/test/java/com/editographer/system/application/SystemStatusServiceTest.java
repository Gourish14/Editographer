package com.editographer.system.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.editographer.system.domain.OllamaProbe;
import com.editographer.system.domain.SystemStatus;
import com.editographer.worker.domain.WorkerClient;
import com.editographer.worker.domain.WorkerStatus;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class SystemStatusServiceTest {

  private final WorkerClient worker = mock(WorkerClient.class);
  private final OllamaProbe ollama = mock(OllamaProbe.class);
  private final SystemStatusService service = new SystemStatusService(worker, ollama);

  @Test
  void combinesWorkerAndOllamaHealth() {
    WorkerStatus.Gpu gpu = new WorkerStatus.Gpu("RTX 3050", 5000L, 55);
    when(worker.status()).thenReturn(Optional.of(new WorkerStatus(true, "job", gpu)));
    when(ollama.isRunning()).thenReturn(true);

    assertThat(service.currentStatus()).isEqualTo(new SystemStatus(true, true, true, gpu));
  }

  @Test
  void aWorkerThatIsDownIsReportedRatherThanFailing() {
    when(worker.status()).thenReturn(Optional.empty());
    when(ollama.isRunning()).thenReturn(false);

    assertThat(service.currentStatus()).isEqualTo(new SystemStatus(false, false, false, null));
  }
}
