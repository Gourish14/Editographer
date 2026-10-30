package com.editographer.system.api;

import static org.assertj.core.api.Assertions.assertThat;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;

class ClientLogControllerTest {

  private final Logger logger = (Logger) LoggerFactory.getLogger(ClientLogController.class);
  private final ListAppender<ILoggingEvent> appender = new ListAppender<>();
  private final ClientLogController controller =
      new ClientLogController(Clock.fixed(Instant.EPOCH, ZoneOffset.UTC));

  @BeforeEach
  void listen() {
    appender.start();
    logger.addAppender(appender);
  }

  @AfterEach
  void stopListening() {
    logger.detachAppender(appender);
  }

  @Test
  void aBrowserErrorReachesTheLog() {
    controller.record(new ClientLogController.ClientLog("boom"));

    assertThat(appender.list).hasSize(1);
    assertThat(appender.list.get(0).getFormattedMessage()).isEqualTo("boom");
  }

  @Test
  void aFloodIsCutOffAfterTenAMinute() {
    for (int index = 0; index < 25; index++) {
      controller.record(new ClientLogController.ClientLog("boom"));
    }

    assertThat(appender.list).hasSize(10);
  }

  @Test
  void aVeryLongMessageIsCut() {
    controller.record(new ClientLogController.ClientLog("x".repeat(2000)));

    assertThat(appender.list.get(0).getFormattedMessage()).hasSize(500);
  }
}
