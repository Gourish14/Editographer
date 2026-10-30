package com.editographer.worker.domain;

import java.util.UUID;

/**
 * Body of POST /jobs/analyze. Paths are relative to the media folder. proxySource is the matching
 * Osmo .LRF, if one was uploaded.
 */
public record AnalyzeJobRequest(
    UUID jobId, UUID assetId, String path, String type, String proxySource) {}
