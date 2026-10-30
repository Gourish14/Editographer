"""Tests for the shared error catalog. Spec: specs/11-coding-standards.md#7-error-codes [T-108]"""

from __future__ import annotations

import re
from pathlib import Path

from app.domain.errors import AnalysisError, ErrorCode, JobCancelledError, RenderError

JAVA_ENUM = (
    Path(__file__).resolve().parents[3]
    / "backend/src/main/java/com/editographer/common/error/ErrorCode.java"
)


def test_error_codes_match_the_java_enum_exactly() -> None:
    java_codes = set(re.findall(r"^\s+([A-Z_]+)\(HttpStatus", JAVA_ENUM.read_text(), re.MULTILINE))

    assert java_codes
    assert {code.value for code in ErrorCode} == java_codes


def test_analysis_and_render_errors_carry_their_default_codes() -> None:
    assert AnalysisError("x").code is ErrorCode.ANALYSIS_FAILED
    assert RenderError("x").code is ErrorCode.RENDER_FAILED


def test_a_specific_code_overrides_the_default() -> None:
    assert RenderError("x", ErrorCode.GPU_OUT_OF_MEMORY).code is ErrorCode.GPU_OUT_OF_MEMORY


def test_cancellation_uses_the_cancelled_code() -> None:
    assert JobCancelledError().code is ErrorCode.RENDER_CANCELLED
