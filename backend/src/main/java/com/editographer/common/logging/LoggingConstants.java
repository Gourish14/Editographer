package com.editographer.common.logging;

/** Field and header names shared by all logging code. Spec: specs/11-coding-standards.md#6 */
public final class LoggingConstants {

  public static final String REQUEST_ID_HEADER = "X-Request-Id";

  public static final String REQUEST_ID = "requestId";
  public static final String JOB_ID = "jobId";
  public static final String RENDER_ID = "renderId";

  public static final String EVENT = "event";
  public static final String DURATION_MS = "durationMs";
  public static final String ERROR_CODE = "errorCode";

  private LoggingConstants() {}
}
