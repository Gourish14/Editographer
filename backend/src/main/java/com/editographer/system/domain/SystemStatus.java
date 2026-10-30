package com.editographer.system.domain;

import com.editographer.worker.domain.WorkerStatus;

/** The health of everything the app relies on. Gpu is null while the worker is unreachable. */
public record SystemStatus(
    boolean workerOnline, boolean workerBusy, boolean ollamaOnline, WorkerStatus.Gpu gpu) {}
