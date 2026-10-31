"""Shot detection with PySceneDetect. Spec: specs/05-editing-brain.md#b2-shot-scoring-scoringpy"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from statistics import median

from scenedetect import ContentDetector, SceneManager, StatsManager, open_video

CONTENT_METRIC = "content_val"
BASE_THRESHOLD = 27.0  # PySceneDetect's own default for ContentDetector
SHAKY_CUT_FACTOR = 2.5


def cut_threshold(frame_changes: Sequence[float], base: float) -> float:
    """How big a frame-to-frame change must be to count as a cut in this clip.

    The detector's fixed threshold suits steady footage, where a change of 3 to 8 is normal. In
    a shaky POV clip every frame changes by 20, so the fixed 27 sits just above the clip's normal
    and fires on every shake. A cut has to stand out 2.5 times above the clip's own median change
    (never below the fixed threshold), so a steady clip is untouched.
    """
    return max(base, SHAKY_CUT_FACTOR * median(frame_changes)) if frame_changes else base


def real_cuts(changes: Mapping[int, float], cuts: Sequence[int], base: float) -> list[int]:
    """The detected cut frames that clear the clip's own threshold."""
    threshold = cut_threshold(list(changes.values()), base)
    return [frame for frame in cuts if changes.get(frame, threshold) >= threshold]


class SceneDetectShots:
    def detect(self, path: Path) -> tuple[tuple[float, float], ...]:
        video = open_video(str(path))
        stats = StatsManager()
        manager = SceneManager(stats)
        manager.add_detector(ContentDetector(threshold=BASE_THRESHOLD))
        manager.detect_scenes(video)
        scenes = manager.get_scene_list()
        if len(scenes) < 2:
            return tuple((start.seconds, end.seconds) for start, end in scenes)

        changes = {
            frame: stats.get_metrics(frame, [CONTENT_METRIC])[0]
            for frame in range(video.frame_number + 1)
            if stats.metrics_exist(frame, [CONTENT_METRIC])
        }
        starts = {start.get_frames(): start for start, _ in scenes}
        kept = set(real_cuts(changes, [frame for frame in starts if frame > 0], BASE_THRESHOLD))
        edges = [scenes[0][0], *(start for frame, start in starts.items() if frame in kept)]
        ends = [*edges[1:], scenes[-1][1]]
        return tuple((start.seconds, end.seconds) for start, end in zip(edges, ends, strict=True))
