package com.editographer.common.config;

import java.time.Clock;
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Supplies the application clock so time-dependent code stays testable. It ticks in microseconds,
 * the database's precision, so a value reads back exactly as it was written.
 */
@Configuration
public class ClockConfig {

  private static final Duration DATABASE_PRECISION = Duration.ofNanos(1000);

  @Bean
  public Clock clock() {
    return Clock.tick(Clock.systemUTC(), DATABASE_PRECISION);
  }
}
