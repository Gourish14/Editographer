package com.editographer.job.application;

import com.editographer.job.domain.Job;
import com.editographer.job.domain.JobKind;

/** Hands one kind of job to the worker. New kinds register a new sender. */
public interface JobSender {

  JobKind kind();

  /** Sends the job. Returns false when what it refers to no longer exists. */
  boolean send(Job job);
}
