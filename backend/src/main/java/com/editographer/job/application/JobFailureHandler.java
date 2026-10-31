package com.editographer.job.application;

import com.editographer.job.domain.Job;

/** Tells whatever the job was for (a render or an asset) that the job gave up. */
public interface JobFailureHandler {

  void jobAbandoned(Job job, String error);
}
