package com.editographer.worker.domain;

import java.util.UUID;

/** Body of POST /jobs/analyze. The path is relative to the media folder. */
public record AnalyzeJobRequest(UUID jobId, UUID assetId, String path, String type) {}
