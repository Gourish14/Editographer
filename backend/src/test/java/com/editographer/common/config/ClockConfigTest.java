package com.editographer.common.config;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.temporal.ChronoField;
import org.junit.jupiter.api.Test;

class ClockConfigTest {

  @Test
  void ticksInDatabasePrecision() {
    int nanos = new ClockConfig().clock().instant().get(ChronoField.NANO_OF_SECOND);

    assertThat(nanos % 1000).isZero();
  }
}
