package com.editographer.common.config;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

/** Turns on the job dispatcher. Tests switch it off and call the dispatcher directly. */
@Configuration
@EnableScheduling
@ConditionalOnProperty(name = "app.scheduling-enabled", havingValue = "true", matchIfMissing = true)
public class SchedulingConfig {}
