"""Stable error codes, shared with the backend. Spec: specs/11-coding-standards.md#7-error-codes"""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    PROJECT_NOT_FOUND = "PROJECT_NOT_FOUND"
    ASSET_NOT_FOUND = "ASSET_NOT_FOUND"
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    RENDER_NOT_FOUND = "RENDER_NOT_FOUND"
    UPLOAD_FAILED = "UPLOAD_FAILED"
    ASSET_UNSUPPORTED = "ASSET_UNSUPPORTED"
    ANALYSIS_FAILED = "ANALYSIS_FAILED"
    WORKER_UNAVAILABLE = "WORKER_UNAVAILABLE"
    GPU_OUT_OF_MEMORY = "GPU_OUT_OF_MEMORY"
    LLM_INVALID_OUTPUT = "LLM_INVALID_OUTPUT"
    PLAN_INVALID = "PLAN_INVALID"
    RENDER_FAILED = "RENDER_FAILED"
    RENDER_CANCELLED = "RENDER_CANCELLED"
    RENDER_NOT_READY = "RENDER_NOT_READY"
    RENDER_ALREADY_FINISHED = "RENDER_ALREADY_FINISHED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    REQUEST_INVALID = "REQUEST_INVALID"
    WORKER_TOKEN_INVALID = "WORKER_TOKEN_INVALID"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class WorkerError(Exception):
    """A failure with a code the backend and UI understand."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


class AnalysisError(WorkerError):
    def __init__(self, message: str, code: ErrorCode = ErrorCode.ANALYSIS_FAILED) -> None:
        super().__init__(code, message)


class RenderError(WorkerError):
    def __init__(self, message: str, code: ErrorCode = ErrorCode.RENDER_FAILED) -> None:
        super().__init__(code, message)


class JobCancelledError(WorkerError):
    def __init__(self) -> None:
        super().__init__(ErrorCode.RENDER_CANCELLED, "The job was cancelled")
