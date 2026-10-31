# 06 — Edit plan and constraint schemas

## Edit plan

The brain outputs one JSON edit plan per render; the compositor renders exactly what it says. Times are seconds on the music timeline; every `at` is snapped to a beat. Saved as `media/renders/{renderId}/plan.json` and in the `render_job.edit_plan` column.

```json
{
  "version": 1,
  "seed": 42,
  "style": "velocity",
  "output": { "ratio": "9:16", "quality": "8K", "width": 4320, "height": 7680, "fps": 60, "mode": "fast" },
  "music": { "assetId": "m1", "start": 12.4, "end": 42.9, "bpm": 128 },
  "grade": { "lut": "teal_orange", "intensity": 0.8, "grain": 0.15 },
  "segments": [
    {
      "id": "s1",
      "assetId": "v3",
      "type": "video",
      "srcIn": 4.20, "srcOut": 6.10,
      "at": 12.40, "duration": 0.94,
      "speed": { "curve": [[0, 2.5], [0.4, 2.5], [0.5, 0.25], [0.8, 0.25], [1.0, 1.0]], "interpolate": "native|rife|none" },
      "reframe": { "mode": "track|center|static", "subject": "person_1" },
      "keyframes": [
        { "t": 0.0, "scale": 1.0, "rotate": 0, "x": 0, "y": 0, "ease": "easeOutExpo" },
        { "t": 0.3, "scale": 1.35, "rotate": -4 }
      ],
      "effects": [
        { "type": "shake", "at": 0.0, "duration": 0.25, "strength": 0.7 },
        { "type": "flash", "at": 0.0, "duration": 0.08 },
        { "type": "motionBlur", "amount": 0.6 }
      ],
      "transitionOut": { "type": "zoom_whip", "duration": 0.18 },
      "source": { "cameraMode": "SINGLE_BOOST_4K", "logProfile": "DLOGM", "nativeFps": 120 },
      "keepAudio": false
    },
    {
      "id": "s2",
      "assetId": "p1",
      "type": "photo",
      "at": 13.34, "duration": 0.47,
      "motion": { "type": "parallax|kenburns", "depth": true, "direction": "push_in", "focusX": 0.62, "focusY": 0.4 }
    },
    {
      "id": "s3",
      "assetId": "v7",
      "type": "video360",
      "srcIn": 10.0, "srcOut": 11.2,
      "at": 13.81, "duration": 0.94,
      "camera360": {
        "projection": "rectilinear",
        "follow": "person_1",
        "keyframes": [
          { "t": 0.00, "yaw": 0,   "pitch": -5,  "roll": 0, "fov": 100, "ease": "easeOutExpo" },
          { "t": 0.47, "yaw": 360, "pitch": -5,  "roll": 0, "fov": 100 },
          { "t": 0.94, "yaw": 360, "pitch": -90, "roll": 0, "fov": 160, "projection": "tinyplanet" }
        ]
      },
      "source": { "cameraMode": "OSMO360_PANO_8K", "logProfile": "DLOGM", "nativeFps": 50 }
    }
  ],
  "text": [
    { "content": "NEXT LEVEL", "at": 20.0, "duration": 1.4, "anim": "pop_on_beat", "behindSubject": true }
  ],
  "sfx": [ { "type": "whoosh", "at": 13.20, "gainDb": -18 } ],
  "log": [ "Prompt request 'add drone shots' skipped: no matching footage" ]
}
```

### Enumerations

| Field | Values |
| --- | --- |
| `style` | velocity, hype, cinematic, anime, travel, car, sports |
| `segment.type` | video, video360, photo |
| `effects[].type` | shake, flash, zoomPunch, motionBlur, glow, lightLeak, rgbSplit, chromatic, vhs, grain, freeze, reverse |
| `transitionOut.type` | cut, zoom_whip, whip_left, whip_right, spin, glitch, flash, luma_fade, zoom_through, planet_morph |
| `camera360.projection` | rectilinear, tinyplanet, rabbithole |
| `ease` | linear, easeInOutCubic, easeOutExpo, easeInExpo, bezier(0.7,0,0.3,1) |
| `source.cameraMode` | see `08-osmo360.md` |

A `transitionOut` plays inside the last frames of its own segment and finishes on the segment's last frame, so the next segment still starts on its beat and frame counts never change. `planet_morph` renders as an FFmpeg circle wipe until a 360 shader exists. `keepAudio` keeps a segment's clip audio and ducks the music under it (B8); it defaults to false. When `sfx` is empty, a whoosh peaking on each transition's cut and an impact on each drop hit are derived from the plan.

`motion.focusX` and `motion.focusY` are the point a photo pushes toward, as shares of the frame (default 0.5, the center). In `camera360.keyframes`, `ease` shapes the span that starts at that keyframe, and a span uses the projection of its end keyframe, else of its start keyframe, else `camera360.projection`.

## Prompt constraint JSON

Produced by the LLM (B9) from the user's prompt; every field is optional.

```json
{
  "style": "cinematic",
  "includeTags": ["car"],
  "excludeTags": [],
  "slowmoAt": ["drop"],
  "fxIntensity": 0.4,
  "effectsOn": ["tinyplanet"],
  "effectsOff": ["shake"],
  "durationSec": 30,
  "text": ["GOA 2026"],
  "order": "chronological",
  "unmapped": ["add drone shots"]
}
```

## Prompt examples

| Prompt | Resulting change |
| --- | --- |
| "slow-mo on the drop" | `slowmoAt: ["drop"]` → drop slots get the B6 ramp |
| "use only the car shots" | `includeTags: ["car"]`, other shots excluded unless too few |
| "cinematic, no shakes" | `style: cinematic`, `effectsOff: ["shake"]` |
| "30 seconds, add text GOA 2026" | `durationSec: 30`, `text: ["GOA 2026"]` |
| (empty) | No constraints; style auto-picked |
