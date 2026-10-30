package com.editographer.worker.api.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.util.UUID;

/** Body of POST /internal/preview-ready. */
public record PreviewReadyRequest(@NotNull UUID jobId, @NotBlank String path) {}
