package com.editographer.common.config;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.nio.file.Path;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

/** Application settings, read from config/local.env through application.yml. */
@ConfigurationProperties("app")
@Validated
public record AppProperties(
    @NotNull Path mediaDir, @NotBlank String workerUrl, @NotBlank String workerToken) {}
