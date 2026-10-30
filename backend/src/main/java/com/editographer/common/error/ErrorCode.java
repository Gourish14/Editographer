package com.editographer.common.error;

import org.springframework.http.HttpStatus;

/**
 * Stable error codes shared with the worker's Python enum. Spec:
 * specs/11-coding-standards.md#7-error-codes
 */
public enum ErrorCode {
  PROJECT_NOT_FOUND(HttpStatus.NOT_FOUND),
  ASSET_NOT_FOUND(HttpStatus.NOT_FOUND),
  JOB_NOT_FOUND(HttpStatus.NOT_FOUND),
  RENDER_NOT_FOUND(HttpStatus.NOT_FOUND),
  UPLOAD_FAILED(HttpStatus.BAD_REQUEST),
  ASSET_UNSUPPORTED(HttpStatus.UNSUPPORTED_MEDIA_TYPE),
  ANALYSIS_FAILED(HttpStatus.INTERNAL_SERVER_ERROR),
  WORKER_UNAVAILABLE(HttpStatus.SERVICE_UNAVAILABLE),
  GPU_OUT_OF_MEMORY(HttpStatus.INTERNAL_SERVER_ERROR),
  LLM_INVALID_OUTPUT(HttpStatus.BAD_GATEWAY),
  PLAN_INVALID(HttpStatus.UNPROCESSABLE_CONTENT),
  RENDER_FAILED(HttpStatus.INTERNAL_SERVER_ERROR),
  RENDER_CANCELLED(HttpStatus.CONFLICT),
  RENDER_NOT_READY(HttpStatus.CONFLICT),
  RENDER_ALREADY_FINISHED(HttpStatus.CONFLICT),
  VALIDATION_FAILED(HttpStatus.BAD_REQUEST),
  REQUEST_INVALID(HttpStatus.BAD_REQUEST),
  WORKER_TOKEN_INVALID(HttpStatus.UNAUTHORIZED),
  INTERNAL_ERROR(HttpStatus.INTERNAL_SERVER_ERROR);

  private final HttpStatus status;

  ErrorCode(HttpStatus status) {
    this.status = status;
  }

  public HttpStatus status() {
    return status;
  }
}
