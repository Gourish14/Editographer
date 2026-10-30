package com.editographer.worker.api.dto;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import java.util.UUID;
import tools.jackson.databind.JsonNode;

/** Body of POST /internal/complete. */
public record JobCompleteRequest(
    @NotNull UUID jobId,
    @NotNull @Pattern(regexp = "DONE|FAILED") String status,
    String outputPath,
    JsonNode plan,
    String error) {}
