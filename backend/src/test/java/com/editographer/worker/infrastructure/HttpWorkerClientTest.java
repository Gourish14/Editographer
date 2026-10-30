package com.editographer.worker.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.editographer.common.config.AppProperties;
import com.editographer.common.error.ApiException;
import com.editographer.common.error.ErrorCode;
import com.editographer.common.logging.LoggingConstants;
import com.editographer.worker.domain.AnalyzeJobRequest;
import com.editographer.worker.domain.WorkerStatus;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.web.client.RestClient;

/** Talks to a real local socket, so headers and JSON are what the worker will actually see. */
class HttpWorkerClientTest {

  private static final String TOKEN = "secret";
  private static final String HEALTH =
      "{\"busy\":false,\"currentJobId\":null,\"gpu\":"
          + "{\"name\":\"RTX 3050\",\"vramFreeMb\":5000,\"tempC\":55},\"extra\":true}";

  private final Map<String, HttpExchange> received = new ConcurrentHashMap<>();
  private final Map<String, String> bodies = new ConcurrentHashMap<>();
  private HttpServer server;
  private int status = 202;
  private String response = "";

  @BeforeEach
  void startServer() throws IOException {
    server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
    server.createContext(
        "/",
        exchange -> {
          received.put(exchange.getRequestURI().getPath(), exchange);
          bodies.put(
              exchange.getRequestURI().getPath(),
              new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
          byte[] bytes = response.getBytes(StandardCharsets.UTF_8);
          exchange.getResponseHeaders().add("Content-Type", "application/json");
          exchange.sendResponseHeaders(status, bytes.length == 0 ? -1 : bytes.length);
          if (bytes.length > 0) {
            exchange.getResponseBody().write(bytes);
          }
          exchange.close();
        });
    server.start();
  }

  @AfterEach
  void stopServer() {
    server.stop(0);
    MDC.clear();
  }

  private HttpWorkerClient client(int port) {
    AppProperties properties =
        new AppProperties(Path.of("media"), "http://127.0.0.1:" + port, TOKEN, "http://unused");
    return new HttpWorkerClient(RestClient.builder(), properties);
  }

  private HttpWorkerClient client() {
    return client(server.getAddress().getPort());
  }

  @Test
  void readsTheStatusAndIgnoresFieldsItDoesNotKnow() {
    response = HEALTH;
    status = 200;

    WorkerStatus worker = client().status().orElseThrow();

    assertThat(worker.busy()).isFalse();
    assertThat(worker.gpu().name()).isEqualTo("RTX 3050");
    assertThat(worker.gpu().vramFreeMb()).isEqualTo(5000L);
    assertThat(worker.gpu().tempC()).isEqualTo(55);
  }

  @Test
  void anIdleWorkerCountsAsIdleAndABusyOneDoesNot() {
    status = 200;
    response = HEALTH;
    assertThat(client().isIdle()).isTrue();

    response = HEALTH.replace("\"busy\":false", "\"busy\":true");
    assertThat(client().isIdle()).isFalse();
  }

  @Test
  void anUnreachableWorkerHasNoStatus() {
    int closedPort = server.getAddress().getPort();
    server.stop(0);

    assertThat(client(closedPort).status()).isEmpty();
    assertThat(client(closedPort).isIdle()).isFalse();
  }

  @Test
  void submittingAJobSendsTokenRequestIdAndJson() {
    MDC.put(LoggingConstants.REQUEST_ID, "req-1");
    UUID jobId = UUID.randomUUID();

    client()
        .submitAnalyze(new AnalyzeJobRequest(jobId, UUID.randomUUID(), "uploads/a.mp4", "VIDEO"));

    HttpExchange exchange = received.get("/jobs/analyze");
    assertThat(exchange.getRequestHeaders().getFirst("X-Worker-Token")).isEqualTo(TOKEN);
    assertThat(exchange.getRequestHeaders().getFirst("X-Request-Id")).isEqualTo("req-1");
    assertThat(bodies.get("/jobs/analyze"))
        .contains("\"jobId\":\"" + jobId + "\"")
        .contains("\"path\":\"uploads/a.mp4\"")
        .contains("\"type\":\"VIDEO\"");
  }

  @Test
  void cancelPostsToTheJobsCancelPath() {
    UUID jobId = UUID.randomUUID();

    client().cancel(jobId);

    assertThat(received).containsKey("/jobs/" + jobId + "/cancel");
  }

  @Test
  void aRefusedJobBecomesWorkerUnavailable() {
    status = 409;
    AnalyzeJobRequest request =
        new AnalyzeJobRequest(UUID.randomUUID(), UUID.randomUUID(), "a.mp4", "VIDEO");

    assertThatThrownBy(() -> client().submitAnalyze(request))
        .isInstanceOfSatisfying(
            ApiException.class,
            error -> assertThat(error.errorCode()).isEqualTo(ErrorCode.WORKER_UNAVAILABLE));
  }
}
