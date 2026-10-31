"""Music map. Spec: specs/05-editing-brain.md#b1-music-map-music_mappy

Pure and deterministic: everything comes in as plain numbers.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import fmean, median

from app.domain.music import Beat, EditWindow, MusicMap, Section, SectionKind

ENERGY_SMOOTHING_SEC = 0.5
ACCENT_SHARE = 0.15
BOUNDARY_CHANGE = 0.3
BARS_COMPARED = 4
DROP_MIN_ENERGY = 0.6
BREAK_MAX_ENERGY = 0.4
BUILD_MIN_BARS = 4
BUILD_MIN_RISE = 0.1
HALF_TEMPO_ABOVE_BPM = 140.0
HALF_TEMPO_PULSE_RATIO = 2.0
MIN_BEATS_FOR_TEMPO_CHECK = 16
MIN_DOWNBEAT_GAP_BEATS = 1.5
BEAT_MATCH_SEC = 0.02
LEAD_IN_BARS = 8
DEFAULT_LENGTH_SEC = 60.0
ONSET_SEARCH_SEC = 0.05
BEATS_PER_BAR_WHEN_UNKNOWN = 4
SECONDS_PER_MINUTE = 60.0
BPM_SPAN_BEATS = 16


@dataclass(frozen=True)
class MusicFeatures:
    """Raw measurements from the audio adapters. Curves are sampled every hop_sec."""

    duration_sec: float
    beats: tuple[float, ...]
    downbeats: tuple[float, ...]
    rms: tuple[float, ...]
    onset_strength: tuple[float, ...]
    hop_sec: float
    brightness: tuple[float, ...] = ()


def build_music_map(features: MusicFeatures, length_sec: float = DEFAULT_LENGTH_SEC) -> MusicMap:
    """B1: beats with strength, energy curve, accents, sections and the edit window."""
    if len(features.beats) < 2:
        raise ValueError("A music map needs at least two beats")
    times, downbeats = _beat_grid(features)
    energy = _energy_curve(features.rms, features.hop_sec)
    loudness = _smooth(features.rms, features.hop_sec)
    brightness = _smooth(features.brightness, features.hop_sec)
    if len(brightness) != len(loudness):
        brightness = []
    intensity = _intensity(loudness, brightness)
    beats = _strengths(times, features.onset_strength, features.hop_sec)
    sections = _sections(
        downbeats, intensity, [loudness, brightness], features.hop_sec, features.duration_sec
    )
    return MusicMap(
        bpm=round(SECONDS_PER_MINUTE / _beat_period(times), 2),
        duration_sec=features.duration_sec,
        beats=beats,
        downbeats=downbeats,
        accent_beats=_accents(beats),
        energy=energy,
        energy_hop_sec=features.hop_sec,
        intensity=intensity,
        sections=sections,
        edit_window=choose_edit_window(
            downbeats, sections, intensity, features.hop_sec, features.duration_sec, length_sec
        ),
    )


def choose_edit_window(
    downbeats: Sequence[float],
    sections: Sequence[Section],
    energy: Sequence[float],
    hop_sec: float,
    duration_sec: float,
    length_sec: float,
) -> EditWindow:
    """Starts 8 bars before the first drop, or takes the loudest stretch of a song with none."""
    first_drop = next((s for s in sections if s.kind is SectionKind.DROP), None)
    if first_drop is not None:
        drop_bar = _bar_at(downbeats, first_drop.start)
        start = downbeats[max(0, drop_bar - LEAD_IN_BARS)]
        return EditWindow(start=start, end=_end_on_downbeat(downbeats, start, length_sec))
    best = max(
        _full_length_starts(downbeats, length_sec),
        key=lambda start: _mean_between(
            energy, hop_sec, start, _end_on_downbeat(downbeats, start, length_sec)
        ),
    )
    end = _end_on_downbeat(downbeats, best, length_sec)
    return EditWindow(start=best, end=end if end > best else duration_sec)


def _full_length_starts(downbeats: Sequence[float], length_sec: float) -> Sequence[float]:
    """Downbeats that leave room for the whole length, so a loud tail cannot win by being short.

    A song shorter than the length has none, and then only its first downbeat qualifies.
    """
    room = length_sec - fmean(_gaps(downbeats))
    fitting = [start for start in downbeats if downbeats[-1] - start >= room]
    return fitting or downbeats[:1]


def _smooth(values: Sequence[float], hop_sec: float) -> list[float]:
    """Moving average over 0.5 s."""
    radius = max(1, round(ENERGY_SMOOTHING_SEC / hop_sec / 2))
    prefix = [0.0]
    for value in values:
        prefix.append(prefix[-1] + value)
    return [
        (prefix[min(len(values), i + radius + 1)] - prefix[max(0, i - radius)])
        / (min(len(values), i + radius + 1) - max(0, i - radius))
        for i in range(len(values))
    ]


def _energy_curve(rms: Sequence[float], hop_sec: float) -> tuple[float, ...]:
    """RMS loudness, smoothed over 0.5 s, relative to the loudest moment.

    Dividing by the peak, not stretching min to max, keeps a steady song steady: tiny level
    changes stay tiny instead of filling the whole 0..1 range.
    """
    smooth = _smooth(rms, hop_sec)
    peak = max(smooth, default=0.0) or 1.0
    return tuple(value / peak for value in smooth)


def _intensity(loudness: Sequence[float], brightness: Sequence[float]) -> tuple[float, ...]:
    """How full the song sounds, as a rank within the song itself (0 = its quietest moment).

    Compressed electronic music is about as loud at its drop as everywhere else, so peak-relative
    loudness cannot tell the parts apart. Ranking loudness, and brightness when it is known,
    against the song's own moments spreads every song over the whole 0..1 range.
    """
    ranks = _percentile_ranks(loudness)
    if brightness:
        bright = _percentile_ranks(brightness)
        ranks = _percentile_ranks([(a + b) / 2 for a, b in zip(ranks, bright, strict=True)])
    return tuple(round(value, 4) for value in ranks)


def _percentile_ranks(values: Sequence[float]) -> list[float]:
    """Each value's share of the song at or below it, ties sharing their middle rank."""
    if len(values) < 2:
        return [0.5] * len(values)
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        stop = start
        while stop + 1 < len(order) and values[order[stop + 1]] == values[order[start]]:
            stop += 1
        for index in order[start : stop + 1]:
            ranks[index] = (start + stop) / 2 / (len(values) - 1)
        start = stop + 1
    return ranks


def _strengths(times: Sequence[float], onset: Sequence[float], hop_sec: float) -> tuple[Beat, ...]:
    """A beat's strength is the strongest onset right around it."""
    radius = max(1, round(ONSET_SEARCH_SEC / hop_sec))
    raw = []
    for time in times:
        center = round(time / hop_sec)
        nearby = onset[max(0, center - radius) : center + radius + 1]
        raw.append(max(nearby, default=0.0))
    strongest = max(raw, default=0.0) or 1.0
    return tuple(
        Beat(time=time, strength=round(value / strongest, 4))
        for time, value in zip(times, raw, strict=True)
    )


def _accents(beats: Sequence[Beat]) -> tuple[float, ...]:
    """Beats whose onset strength is in the top 15%."""
    count = max(1, math.ceil(len(beats) * ACCENT_SHARE))
    threshold = sorted((beat.strength for beat in beats), reverse=True)[count - 1]
    return tuple(beat.time for beat in beats if beat.strength >= threshold)


def _sections(
    downbeats: Sequence[float],
    intensity: Sequence[float],
    curves: Sequence[Sequence[float]],
    hop_sec: float,
    duration_sec: float,
) -> tuple[Section, ...]:
    edges = [0.0, *_boundaries(downbeats, curves, hop_sec), duration_sec]
    spans = list(zip(edges, edges[1:], strict=False))
    means = [_mean_between(intensity, hop_sec, start, end) for start, end in spans]
    kinds: list[SectionKind] = []
    for index, (start, end) in enumerate(spans):
        kinds.append(
            _section_kind(index, kinds, means, _rise(downbeats, intensity, hop_sec, start, end))
        )
    return tuple(
        Section(kind=kind, start=start, end=end, mean_energy=round(mean, 4))
        for kind, (start, end), mean in zip(kinds, spans, means, strict=True)
    )


def _boundaries(
    downbeats: Sequence[float], curves: Sequence[Sequence[float]], hop_sec: float
) -> list[float]:
    """Downbeats where the sound of the 4 bars after differs from the 4 before.

    Each curve (loudness, brightness) is measured as a share of its own typical value in the song,
    and the changes are added up as a distance. Over 0.3 is a boundary. Judging by the song's own
    scale, not by a fixed loudness, finds the filter sweeps and level steps of compressed music,
    and leaves a steady song whole. A change spreads over neighbouring downbeats, so the biggest
    one wins and the others within 4 bars of it are dropped.
    """
    scaled = [_relative_to_typical(curve) for curve in curves if curve]
    scored: list[tuple[float, int]] = []
    for bar in range(1, len(downbeats) - 1):
        first = downbeats[max(0, bar - BARS_COMPARED)]
        last = downbeats[min(len(downbeats) - 1, bar + BARS_COMPARED)]
        change = math.sqrt(
            sum(
                (
                    _mean_between(curve, hop_sec, downbeats[bar], last)
                    - _mean_between(curve, hop_sec, first, downbeats[bar])
                )
                ** 2
                for curve in scaled
            )
        )
        if change > BOUNDARY_CHANGE:
            scored.append((change, bar))

    chosen: list[int] = []
    for _, bar in sorted(scored, key=lambda item: (-item[0], item[1])):
        if all(abs(bar - other) >= BARS_COMPARED for other in chosen):
            chosen.append(bar)
    return [downbeats[bar] for bar in sorted(chosen)]


def _relative_to_typical(curve: Sequence[float]) -> list[float]:
    typical = median(curve) or 1.0
    return [value / typical for value in curve]


def _section_kind(
    index: int, earlier: Sequence[SectionKind], means: Sequence[float], rise: float | None
) -> SectionKind:
    mean = means[index]
    is_last = index == len(means) - 1
    if index > 0 and mean >= DROP_MIN_ENERGY and means[index - 1] + BUILD_MIN_RISE <= mean:
        return SectionKind.DROP
    if index == 0:
        return SectionKind.INTRO
    if is_last:
        return SectionKind.OUTRO
    if mean < BREAK_MAX_ENERGY and SectionKind.DROP in earlier:
        return SectionKind.BREAK
    if rise is not None and rise >= BUILD_MIN_RISE:
        return SectionKind.BUILD
    return SectionKind.VERSE


def _rise(
    downbeats: Sequence[float],
    energy: Sequence[float],
    hop_sec: float,
    start: float,
    end: float,
) -> float | None:
    """Energy gained from the first bar to the last, or None under 4 bars."""
    bars = [time for time in downbeats if start <= time <= end]
    if len(bars) <= BUILD_MIN_BARS:
        return None
    return _mean_between(energy, hop_sec, bars[-2], bars[-1]) - _mean_between(
        energy, hop_sec, bars[0], bars[1]
    )


def _beat_grid(features: MusicFeatures) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Beats and downbeats to cut on: half-tempo when the music pulses at half the tracked rate.

    A tracker can lock onto the double of the real pulse. Only a fast grid is checked: when the
    onset curve repeats far more strongly every 2 beats than every beat, every other beat is
    kept, starting on the phase that holds the downbeats (else the stronger onsets), so every
    kept beat is a real tracked beat. Downbeats the tracker put closer than 1.5 beats from the
    previous one are spurious and dropped.
    """
    beats, downbeats = features.beats, features.downbeats
    period = _beat_period(beats)
    if (
        len(beats) >= MIN_BEATS_FOR_TEMPO_CHECK
        and SECONDS_PER_MINUTE / period > HALF_TEMPO_ABOVE_BPM
        and _pulse(features.onset_strength, features.hop_sec, 2 * period)
        >= HALF_TEMPO_PULSE_RATIO * _pulse(features.onset_strength, features.hop_sec, period)
    ):
        beats = _half_tempo(beats, downbeats, features.onset_strength, features.hop_sec)
        period *= 2
    if not downbeats:
        return beats, beats[::BEATS_PER_BAR_WHEN_UNKNOWN]
    on_beats = [d for d in downbeats if any(abs(d - b) <= BEAT_MATCH_SEC for b in beats)]
    spaced: list[float] = []
    for time in on_beats:
        if not spaced or time - spaced[-1] >= MIN_DOWNBEAT_GAP_BEATS * period:
            spaced.append(time)
    return beats, tuple(spaced)


def _half_tempo(
    beats: Sequence[float], downbeats: Sequence[float], onset: Sequence[float], hop_sec: float
) -> tuple[float, ...]:
    def score(phase: int) -> tuple[int, float]:
        kept = beats[phase::2]
        held = sum(1 for d in downbeats if any(abs(d - b) <= BEAT_MATCH_SEC for b in kept))
        strength = sum(onset[min(len(onset) - 1, round(b / hop_sec))] for b in kept)
        return held, strength

    return tuple(beats[max((0, 1), key=score) :: 2])


def _pulse(onset: Sequence[float], hop_sec: float, lag_sec: float) -> float:
    """How strongly the onset curve repeats after the lag (autocorrelation, 1 = identical)."""
    mean = fmean(onset)
    centered = [value - mean for value in onset]
    total = sum(value * value for value in centered) or 1.0
    lag = round(lag_sec / hop_sec)
    return max(
        sum(a * b for a, b in zip(centered, centered[shift:], strict=False)) / total
        for shift in (lag - 1, lag, lag + 1)
    )


def _bar_at(downbeats: Sequence[float], time: float) -> int:
    return min(range(len(downbeats)), key=lambda bar: abs(downbeats[bar] - time))


def _end_on_downbeat(downbeats: Sequence[float], start: float, length_sec: float) -> float:
    within = [time for time in downbeats if start < time <= start + length_sec]
    return within[-1] if within else start


def _mean_between(values: Sequence[float], hop_sec: float, start: float, end: float) -> float:
    first = max(0, round(start / hop_sec))
    last = max(first + 1, round(end / hop_sec))
    window = values[first:last]
    return fmean(window) if window else 0.0


def _beat_period(beats: Sequence[float]) -> float:
    """Seconds per beat, measured over several beats.

    Trackers report whole 20 ms frames, so one gap cannot tell 118 from 120 BPM. The median keeps
    a stray beat from mattering.
    """
    span = min(BPM_SPAN_BEATS, len(beats) - 1)
    return median(
        (later - earlier) / span for earlier, later in zip(beats, beats[span:], strict=False)
    )


def _gaps(times: Sequence[float]) -> list[float]:
    return [later - earlier for earlier, later in zip(times, times[1:], strict=False)]
