"""A raw .OSV renders from its stitched file. Spec: specs/08-osmo360.md (rule 3) [T-409]"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.application.render_job import RenderEdit
from app.domain.errors import RenderError
from app.domain.models import AssetInput, AssetType


def renderer(root: Path) -> RenderEdit:
    nothing: Any = None
    return RenderEdit(root, nothing, nothing, nothing, nothing, nothing, nothing)


def osv(path: str) -> AssetInput:
    return AssetInput("a9", AssetType.VIDEO, path, None, None, None, 8.0, 7680, 3840, 30.0)


def test_rule_3_an_osv_renders_from_its_stitched_file(tmp_path: Path) -> None:
    (tmp_path / "stitched").mkdir()
    (tmp_path / "stitched/a9.mp4").write_text("equirect")

    source = renderer(tmp_path)._source_file(osv("uploads/CAM.OSV"))

    assert source == tmp_path / "stitched/a9.mp4"


def test_rule_3_an_osv_that_was_never_stitched_says_so(tmp_path: Path) -> None:
    with pytest.raises(RenderError, match="stitched"):
        renderer(tmp_path)._source_file(osv("uploads/CAM.osv"))


def test_other_files_render_from_their_own_path(tmp_path: Path) -> None:
    assert renderer(tmp_path)._source_file(osv("uploads/a.mp4")) == tmp_path / "uploads/a.mp4"
