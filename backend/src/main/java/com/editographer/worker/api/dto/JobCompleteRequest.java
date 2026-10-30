package com.editographer.worker.api.dto;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import java.util.UUID;

/** Body of POST /internal/complete. Render fields join in T-107. */
public record JobCompleteRequest(
    @NotNull UUID jobId, @NotNull @Pattern(regexp = "DONE|FAILED") String status, String error) {}
