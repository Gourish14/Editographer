package com.editographer.worker.infrastructure;

import com.editographer.common.config.AppProperties;
import com.editographer.common.error.ApiException;
import com.editographer.common.error.ErrorCode;
import com.editographer.common.logging.LoggingConstants;
import com.editographer.worker.domain.AnalyzeJobRequest;
import com.editographer.worker.domain.RenderJobRequest;
import com.editographer.worker.domain.WorkerClient;
import com.editographer.worker.domain.WorkerStatus;
import java.net.http.HttpClient;
import java.time.Duration;
import java.util.Optional;
import java.util.UUID;
import org.slf4j.MDC;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

/** HTTP client for the worker. Spec: specs/07-api-and-data.md#worker-api */
@Component
final class HttpWorkerClient implements WorkerClient {

  private static final String TOKEN_HEADER = "X-Worker-Token";
  private static final Duration CONNECT_TIMEOUT = Duration.ofSeconds(1);
  private static final Duration READ_TIMEOUT = Duration.ofSeconds(5);

  private final RestClient http;

  HttpWorkerClient(RestClient.Builder builder, AppProperties properties) {
    JdkClientHttpRequestFactory requests =
        new JdkClientHttpRequestFactory(
            HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(CONNECT_TIMEOUT)
                .build());
    requests.setReadTimeout(READ_TIMEOUT);
    this.http =
        builder
            .requestFactory(requests)
            .baseUrl(properties.workerUrl())
            .defaultHeader(TOKEN_HEADER, properties.workerToken())
            .build();
  }

  @Override
  public Optional<WorkerStatus> status() {
    try {
      return Optional.ofNullable(http.get().uri("/health").retrieve().body(WorkerStatus.class));
    } catch (RestClientException exception) {
      return Optional.empty();
    }
  }

  @Override
  public void submitAnalyze(AnalyzeJobRequest request) {
    post("/jobs/analyze", request);
  }

  @Override
  public void submitRender(RenderJobRequest request) {
    post("/jobs/render", request);
  }

  @Override
  public void cancel(UUID jobId) {
    post("/jobs/" + jobId + "/cancel", null);
  }

  private void post(String path, Object body) {
    try {
      RestClient.RequestBodySpec request = http.post().uri(path);
      String requestId = MDC.get(LoggingConstants.REQUEST_ID);
      if (requestId != null) {
        request.header(LoggingConstants.REQUEST_ID_HEADER, requestId);
      }
      if (body != null) {
        request.body(body);
      }
      request.retrieve().toBodilessEntity();
    } catch (RestClientException exception) {
      throw new ApiException(
          ErrorCode.WORKER_UNAVAILABLE, "The worker did not accept the request", exception);
    }
  }
}
