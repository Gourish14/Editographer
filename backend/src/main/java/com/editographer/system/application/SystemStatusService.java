package com.editographer.system.application;

import com.editographer.system.domain.OllamaProbe;
import com.editographer.system.domain.SystemStatus;
import com.editographer.worker.domain.WorkerClient;
import com.editographer.worker.domain.WorkerStatus;
import java.util.Optional;
import org.springframework.stereotype.Service;

/** Gathers system health. Spec: specs/07-api-and-data.md (GET /api/system) */
@Service
public class SystemStatusService {

  private final WorkerClient worker;
  private final OllamaProbe ollama;

  public SystemStatusService(WorkerClient worker, OllamaProbe ollama) {
    this.worker = worker;
    this.ollama = ollama;
  }

  public SystemStatus currentStatus() {
    Optional<WorkerStatus> status = worker.status();
    return new SystemStatus(
        status.isPresent(),
        status.map(WorkerStatus::busy).orElse(false),
        ollama.isRunning(),
        status.map(WorkerStatus::gpu).orElse(null));
  }
}
