package com.editographer.worker.api.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.util.UUID;

/** Body of POST /internal/progress. */
public record ProgressRequest(
    @NotNull UUID jobId, @NotBlank String stage, @Min(0) @Max(100) int percent, String message) {}
