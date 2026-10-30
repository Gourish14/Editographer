package com.editographer.worker.infrastructure;

import com.editographer.common.config.AppProperties;
import com.editographer.common.error.ApiException;
import com.editographer.common.error.ErrorCode;
import com.editographer.common.logging.LoggingConstants;
import com.editographer.worker.domain.AnalyzeJobRequest;
import com.editographer.worker.domain.WorkerClient;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

/** HTTP client for the worker. Spec: specs/07-api-and-data.md#worker-api */
@Component
final class HttpWorkerClient implements WorkerClient {

  private static final String TOKEN_HEADER = "X-Worker-Token";

  private final RestClient http;

  HttpWorkerClient(RestClient.Builder builder, AppProperties properties) {
    this.http =
        builder
            .baseUrl(properties.workerUrl())
            .defaultHeader(TOKEN_HEADER, properties.workerToken())
            .build();
  }

  @Override
  public boolean isIdle() {
    try {
      WorkerHealth health = http.get().uri("/health").retrieve().body(WorkerHealth.class);
      return health != null && !health.busy();
    } catch (RestClientException exception) {
      return false;
    }
  }

  @Override
  public void submitAnalyze(AnalyzeJobRequest request) {
    try {
      http.post()
          .uri("/jobs/analyze")
          .header(LoggingConstants.REQUEST_ID_HEADER, MDC.get(LoggingConstants.REQUEST_ID))
          .body(request)
          .retrieve()
          .toBodilessEntity();
    } catch (RestClientException exception) {
      throw new ApiException(
          ErrorCode.WORKER_UNAVAILABLE, "The worker did not accept the job", exception);
    }
  }

  private record WorkerHealth(boolean busy) {}
}
