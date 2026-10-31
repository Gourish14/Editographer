"""The camera360 and motion plan fields. Spec: specs/06-edit-plan-schema.md#edit-plan [T-302]"""

from __future__ import annotations

from app.domain.plan import Camera360, CameraKeyframe, Motion, Segment

OLD_SEGMENT = {
    "id": "s1",
    "assetId": "v3",
    "type": "video",
    "srcIn": 4.2,
    "srcOut": 6.1,
    "at": 12.4,
    "duration": 0.94,
    "source": {"cameraMode": "FLAT", "logProfile": None, "nativeFps": 30},
}
SPEC_PHOTO = {
    "id": "s2",
    "assetId": "p1",
    "type": "photo",
    "at": 13.34,
    "duration": 0.47,
    "motion": {"type": "parallax", "depth": True, "direction": "push_in"},
}
SPEC_360 = {
    "id": "s3",
    "assetId": "v7",
    "type": "video360",
    "srcIn": 10.0,
    "srcOut": 11.2,
    "at": 13.81,
    "duration": 0.94,
    "camera360": {
        "projection": "rectilinear",
        "follow": "person_1",
        "keyframes": [
            {"t": 0.0, "yaw": 0, "pitch": -5, "roll": 0, "fov": 100, "ease": "easeOutExpo"},
            {"t": 0.47, "yaw": 360, "pitch": -5, "roll": 0, "fov": 100},
            {
                "t": 0.94,
                "yaw": 360,
                "pitch": -90,
                "roll": 0,
                "fov": 160,
                "projection": "tinyplanet",
            },
        ],
    },
    "source": {"cameraMode": "OSMO360_PANO_8K", "logProfile": "DLOGM", "nativeFps": 50},
}


def test_schema_a_plan_saved_before_these_fields_stays_valid() -> None:
    segment = Segment.model_validate(OLD_SEGMENT)

    assert segment.camera360 is None
    assert segment.motion is None
    assert segment.src_in == 4.2


def test_schema_the_spec_example_360_segment_parses() -> None:
    camera = Segment.model_validate(SPEC_360).camera360

    assert camera is not None
    assert camera.follow == "person_1"
    assert camera.keyframes[0].ease == "easeOutExpo"
    assert camera.keyframes[1].ease == "linear"
    assert camera.keyframes[1].projection is None
    assert camera.keyframes[2].projection == "tinyplanet"


def test_schema_the_spec_example_photo_segment_parses_without_source_fields() -> None:
    segment = Segment.model_validate(SPEC_PHOTO)

    assert segment.motion == Motion(type="parallax", depth=True)
    assert segment.source.camera_mode is None


def test_schema_camera360_and_motion_round_trip_through_json_aliases() -> None:
    segment = Segment(
        id="s1",
        asset_id="v1",
        type="video360",
        at=0.0,
        duration=1.0,
        camera360=Camera360(keyframes=(CameraKeyframe(t=0.0, yaw=10.0, pitch=-5.0, fov=100.0),)),
        motion=Motion(focus_x=0.25, focus_y=0.75),
    )

    document = segment.model_dump(mode="json", by_alias=True)

    assert document["camera360"]["keyframes"][0]["yaw"] == 10.0
    assert document["motion"]["focusX"] == 0.25
    assert Segment.model_validate(document) == segment
