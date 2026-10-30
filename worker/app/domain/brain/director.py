"""What the LLM director is told.

Spec: specs/05-editing-brain.md#b10-llm-director-and-fallback-directorpy

Pure: building the brief only. Calling the LLM belongs to the application layer.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import get_args

from app.domain.brain.planner import ClipInput, usable_candidates
from app.domain.constraints import StyleId
from app.domain.models import RenderSettings
from app.domain.music import MusicMap, SectionKind

MAX_SHOTS = 40
MAX_TAGS_PER_SHOT = 5
MAX_PROMPT_CHARS = 1000
MAX_SECTIONS = 24
NO_PROMPT = ""

SYSTEM_PROMPT = f"""You direct an automatic music video editor. Reply with one JSON object only:
{{"style": <style or null>, "storyHints": [<short strings>], "constraints": {{...}}}}

style is your pick for this footage and music, one of: {", ".join(get_args(StyleId))}.

constraints holds ONLY what the user's prompt asks for. Leave every other field out. Fields:
- style: only when the prompt names a style. Same values as above.
- includeTags: subjects the prompt wants ("only car shots" gives ["car"]).
- excludeTags: subjects the prompt does not want ("no people" gives ["people"]).
- slowmoAt: music sections for slow motion, from: {", ".join(kind.value for kind in SectionKind)}.
- fxIntensity: number 0 to 1, only when the prompt wants weaker or stronger effects.
- effectsOn: effects the prompt adds, such as "tinyplanet".
- effectsOff: effects the prompt removes, from: shake, flash, zoomPunch.
- durationSec: length in seconds as a number ("30 seconds" gives 30).
- text: words to show on screen, exactly as written.
- order: "chronological" only when the prompt wants time order.
- unmapped: each request that fits none of the fields, in the user's words.

Examples:
"slow-mo on the drop" gives {{"slowmoAt": ["drop"]}}
"use only the car shots" gives {{"includeTags": ["car"]}}
"cinematic, no shakes" gives {{"style": "cinematic", "effectsOff": ["shake"]}}
"30 seconds, add text GOA 2026" gives {{"durationSec": 30, "text": ["GOA 2026"]}}
"add drone shots" gives {{"unmapped": ["add drone shots"]}}
"""


def director_brief(music: MusicMap, clips: Sequence[ClipInput], settings: RenderSettings) -> str:
    """Compact JSON: sections, top shots, user settings and the prompt, ~3,000 tokens at most."""
    modes = {clip.asset_id: clip.analysis.camera_mode for clip in clips}
    top = sorted(usable_candidates(clips), key=lambda c: c.shot.score, reverse=True)[:MAX_SHOTS]
    document = {
        "bpm": round(music.bpm),
        "sections": [
            {
                "type": section.kind.value,
                "start": round(section.start, 1),
                "end": round(section.end, 1),
                "energy": round(section.mean_energy, 2),
            }
            for section in music.sections[:MAX_SECTIONS]
        ],
        "shots": [
            {
                "id": f"{candidate.asset_id}@{candidate.shot.measure.start:g}",
                "tags": candidate.shot.measure.tags[:MAX_TAGS_PER_SHOT],
                "score": round(candidate.shot.score, 2),
                "cameraMode": modes[candidate.asset_id],
            }
            for candidate in top
        ],
        "settings": {
            "style": settings.style,
            "ratio": settings.ratio,
            "lengthSec": settings.length_sec,
        },
        "prompt": (settings.prompt or NO_PROMPT)[:MAX_PROMPT_CHARS],
    }
    return json.dumps(document, separators=(",", ":"), ensure_ascii=False)
