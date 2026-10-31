"""What the LLM director is told.

Spec: specs/05-editing-brain.md#b10-llm-director-and-fallback-directorpy

Pure: building the request only. Calling the LLM belongs to the application layer. The project goes
in the system message and the examples are real chat turns: with the JSON and prompt together in
one user message, qwen3:4b with thinking off echoes its input instead of answering.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, get_args

from app.domain.brain.assign import Candidate
from app.domain.brain.planner import ClipInput, usable_candidates
from app.domain.constraints import StyleId
from app.domain.models import RenderSettings
from app.domain.music import MusicMap, SectionKind

MAX_SHOTS = 40
MAX_TAGS_PER_SHOT = 5
MAX_TAG_CHARS = 24
MAX_CAPTION_CHARS = 80
MAX_PROMPT_CHARS = 1000
MAX_SECTIONS = 24
NO_PROMPT = "No prompt. Pick the style that suits this project."

SYSTEM_PROMPT = f"""You direct an automatic music video editor. Reply with one JSON object only:
{{"style": <style or null>, "storyHints": [<short strings>], "constraints": {{...}}}}

style is your pick for this footage and music, one of: {", ".join(get_args(StyleId))}.

constraints holds ONLY what the user's prompt asks for. Leave every other field out. Fields:
- style: when the prompt names a style. Same values as above.
- includeTags: subjects the prompt wants.
- excludeTags: subjects the prompt does not want.
- slowmoAt: music sections for slow motion, from: {", ".join(kind.value for kind in SectionKind)}.
- fxIntensity: number 0 to 1, when the prompt wants weaker or stronger effects.
- effectsOn: effects the prompt adds, such as "tinyplanet".
- effectsOff: effects the prompt removes, from: shake, flash, zoomPunch.
- durationSec: length in seconds as a number.
- text: words to show on screen, exactly as written.
- order: "chronological" when the prompt wants time order.
- unmapped: each request that fits none of the fields, in the user's words."""

EXAMPLES = (
    (
        "use only the beach shots",
        '{"style":null,"storyHints":[],"constraints":{"includeTags":["beach"]}}',
    ),
    (
        "slow motion on the break, no flashes",
        '{"style":null,"storyHints":[],'
        '"constraints":{"slowmoAt":["break"],"effectsOff":["flash"]}}',
    ),
    (
        "anime, 20 seconds, add text HELLO",
        '{"style":"anime","storyHints":[],'
        '"constraints":{"style":"anime","durationSec":20,"text":["HELLO"]}}',
    ),
    (
        "add underwater shots",
        '{"style":null,"storyHints":[],"constraints":{"unmapped":["add underwater shots"]}}',
    ),
)


@dataclass(frozen=True)
class DirectorRequest:
    system: str
    user: str
    examples: tuple[tuple[str, str], ...] = EXAMPLES


def director_request(
    music: MusicMap, clips: Sequence[ClipInput], settings: RenderSettings
) -> DirectorRequest:
    """The whole request stays near 3,000 tokens at most, however large the project is."""
    prompt = (settings.prompt or "").strip()[:MAX_PROMPT_CHARS]
    project = director_brief(music, clips, settings)
    system = f"{SYSTEM_PROMPT}\n\nProject (context only, never repeat it): {project}"
    return DirectorRequest(system, prompt or NO_PROMPT)


def director_brief(music: MusicMap, clips: Sequence[ClipInput], settings: RenderSettings) -> str:
    """Compact JSON: music sections, the top shots and user settings."""
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
        "shots": [_shot_entry(position, c, modes[c.asset_id]) for position, c in enumerate(top, 1)],
        "settings": {
            "style": settings.style,
            "ratio": settings.ratio,
            "lengthSec": settings.length_sec,
        },
    }
    return json.dumps(document, separators=(",", ":"), ensure_ascii=False)


def _shot_entry(position: int, candidate: Candidate, camera_mode: str | None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": position,
        "tags": [tag[:MAX_TAG_CHARS] for tag in candidate.shot.measure.tags[:MAX_TAGS_PER_SHOT]],
        "score": round(candidate.shot.score, 2),
        "cameraMode": camera_mode,
    }
    caption = candidate.shot.measure.caption.strip()
    if caption:
        entry["caption"] = caption[:MAX_CAPTION_CHARS]
    return entry
