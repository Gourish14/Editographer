package com.editographer.worker.api.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.util.UUID;

/** Body of POST /internal/asset-analyzed. */
public record AssetAnalyzedRequest(
    @NotNull UUID assetId,
    @NotBlank String analysisPath,
    String fileHash,
    String cameraMode,
    String logProfile,
    Double durationSec,
    Integer width,
    Integer height,
    Double fps) {}
