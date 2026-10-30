package com.editographer.worker.application;

import com.editographer.job.domain.JobStatus;
import com.editographer.storage.domain.MediaPath;
import java.util.UUID;

/** What the worker reports when a job ends. Output, plan and error are optional. */
public record JobCompletion(
    UUID jobId, JobStatus status, MediaPath outputPath, String plan, String error) {}
