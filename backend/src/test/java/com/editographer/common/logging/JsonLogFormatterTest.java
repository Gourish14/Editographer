package com.editographer.common.logging;

import static org.assertj.core.api.Assertions.assertThat;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.LoggerContext;
import ch.qos.logback.classic.spi.LoggingEvent;
import ch.qos.logback.classic.util.LogbackMDCAdapter;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.slf4j.event.KeyValuePair;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

class JsonLogFormatterTest {

  private final JsonLogFormatter formatter = new JsonLogFormatter();
  private final ObjectMapper mapper = new ObjectMapper();
  private final LoggerContext context = new LoggerContext();
  private final Logger logger = context.getLogger("com.editographer.Example");

  JsonLogFormatterTest() {
    context.setMDCAdapter(new LogbackMDCAdapter());
  }

  private LoggingEvent event(Level level, String message, Throwable cause) {
    return new LoggingEvent("fqcn", logger, level, message, cause, new Object[0]);
  }

  @Test
  void writesTheSpecFieldsAsOneJsonLine() {
    LoggingEvent event = event(Level.INFO, "Stage finished", null);
    event.setMDCPropertyMap(
        Map.of(LoggingConstants.REQUEST_ID, "req-1", LoggingConstants.JOB_ID, "job-1"));
    event.addKeyValuePair(new KeyValuePair(LoggingConstants.EVENT, "stage.finished"));
    event.addKeyValuePair(new KeyValuePair(LoggingConstants.DURATION_MS, 42L));

    String line = formatter.format(event);

    assertThat(line).endsWith("\n");
    assertThat(line.strip()).doesNotContain("\n");
    JsonNode json = mapper.readTree(line);
    assertThat(json.path("ts").asString()).isNotBlank();
    assertThat(json.path("level").asString()).isEqualTo("INFO");
    assertThat(json.path("service").asString()).isEqualTo("backend");
    assertThat(json.path("requestId").asString()).isEqualTo("req-1");
    assertThat(json.path("jobId").asString()).isEqualTo("job-1");
    assertThat(json.path("event").asString()).isEqualTo("stage.finished");
    assertThat(json.path("message").asString()).isEqualTo("Stage finished");
    assertThat(json.path("durationMs").asLong()).isEqualTo(42L);
  }

  @Test
  void omitsEmptyFieldsAndFallsBackToTheLoggerName() {
    JsonNode json = mapper.readTree(formatter.format(event(Level.WARN, "x", null)));

    assertThat(json.has("requestId")).isFalse();
    assertThat(json.has("jobId")).isFalse();
    assertThat(json.has("errorCode")).isFalse();
    assertThat(json.has("exception")).isFalse();
    assertThat(json.path("event").asString()).isEqualTo("com.editographer.Example");
  }

  @Test
  void keepsStackTracesOnASingleLine() {
    String line = formatter.format(event(Level.ERROR, "x", new IllegalStateException("boom")));

    assertThat(line.strip()).doesNotContain("\n");
    assertThat(mapper.readTree(line).path("exception").asString()).contains("boom");
  }

  @Test
  void keyValueLookupIgnoresUnrelatedPairs() {
    LoggingEvent event = event(Level.INFO, "x", null);
    event.setKeyValuePairs(
        List.of(new KeyValuePair("other", "y"), new KeyValuePair("errorCode", "RENDER_FAILED")));

    JsonNode json = mapper.readTree(formatter.format(event));

    assertThat(json.path("errorCode").asString()).isEqualTo("RENDER_FAILED");
    assertThat(json.has("other")).isFalse();
  }
}
