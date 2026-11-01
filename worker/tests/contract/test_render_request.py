"""The render request the backend sends: settings.followPoint with its clip. [CR-014]

Spec: specs/07-api-and-data.md (POST /api/projects/{id}/renders), specs/08-osmo360.md rule 5.
The JSON below is the shape of the backend's `RenderSettings` record.
"""

from __future__ import annotations

from app.api.schemas import RenderSettingsBody

BASE = {"ratio": "9:16", "quality": "4K", "fps": 30, "style": "auto", "mode": "fast", "seed": 7}


def settings_with(follow: object) -> RenderSettingsBody:
    return RenderSettingsBody.model_validate({**BASE, "followPoint": follow})


def test_07_follow_point_carries_the_asset_id_of_its_360_clip() -> None:
    body = {"x": 0.25, "y": 0.5, "timeSec": 3.5, "assetId": "8d3c0f0e-1111-4222-8333-444455556666"}

    point = settings_with(body).to_settings().follow_point

    assert point is not None
    assert (point.x, point.y, point.time_sec) == (0.25, 0.5, 3.5)
    assert point.asset_id == "8d3c0f0e-1111-4222-8333-444455556666"


def test_07_follow_point_without_an_asset_id_or_with_null_still_parses() -> None:
    for body in (
        {"x": 0.25, "y": 0.5, "timeSec": 3.5},
        {"x": 0.25, "y": 0.5, "timeSec": 3.5, "assetId": None},
    ):
        point = settings_with(body).to_settings().follow_point

        assert point is not None
        assert point.asset_id is None


def test_07_no_follow_point_stays_none() -> None:
    assert settings_with(None).to_settings().follow_point is None
