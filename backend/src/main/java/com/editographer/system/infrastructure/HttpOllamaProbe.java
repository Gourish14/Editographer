package com.editographer.system.infrastructure;

import com.editographer.common.config.AppProperties;
import com.editographer.system.domain.OllamaProbe;
import java.net.http.HttpClient;
import java.time.Duration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

/** Asks Ollama for its version, the cheapest call it has. */
@Component
final class HttpOllamaProbe implements OllamaProbe {

  private static final Duration TIMEOUT = Duration.ofSeconds(1);

  private final RestClient http;

  HttpOllamaProbe(RestClient.Builder builder, AppProperties properties) {
    JdkClientHttpRequestFactory requests =
        new JdkClientHttpRequestFactory(
            HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(TIMEOUT)
                .build());
    requests.setReadTimeout(TIMEOUT);
    this.http = builder.requestFactory(requests).baseUrl(properties.ollamaUrl()).build();
  }

  @Override
  public boolean isRunning() {
    try {
      http.get().uri("/api/version").retrieve().toBodilessEntity();
      return true;
    } catch (RestClientException exception) {
      return false;
    }
  }
}
