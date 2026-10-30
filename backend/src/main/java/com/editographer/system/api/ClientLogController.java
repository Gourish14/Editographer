package com.editographer.system.api;

import com.editographer.common.logging.LoggingConstants;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import java.time.Clock;
import java.time.Instant;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/**
 * Takes browser errors into the backend log, at most a few a minute. Spec:
 * specs/11-coding-standards.md#6-logging-all-three-apps
 */
@RestController
public final class ClientLogController {

  private static final Logger LOG = LoggerFactory.getLogger(ClientLogController.class);
  private static final int MAX_PER_MINUTE = 10;
  private static final int MAX_MESSAGE_CHARS = 500;
  private static final long MINUTE_SECONDS = 60L;

  private final Clock clock;
  private long windowStart;
  private int countInWindow;

  public ClientLogController(Clock clock) {
    this.clock = clock;
  }

  /** The browser's report of an error. */
  public record ClientLog(@NotBlank String message) {}

  @PostMapping("/api/client-logs")
  @ResponseStatus(HttpStatus.NO_CONTENT)
  public void record(@Valid @RequestBody ClientLog log) {
    if (withinLimit(clock.instant())) {
      String message = log.message();
      LOG.atWarn()
          .addKeyValue(LoggingConstants.EVENT, "client.error")
          .log(message.substring(0, Math.min(message.length(), MAX_MESSAGE_CHARS)));
    }
  }

  private synchronized boolean withinLimit(Instant now) {
    long minute = now.getEpochSecond() / MINUTE_SECONDS;
    if (minute != windowStart) {
      windowStart = minute;
      countInWindow = 0;
    }
    countInWindow++;
    return countInWindow <= MAX_PER_MINUTE;
  }
}
