package com.editographer.render.domain;

import java.time.Instant;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

/**
 * What the user chose for a render. A null lengthSec means Auto. Spec:
 * specs/00-overview.md#user-choices. A null startAt starts as soon as the worker is free ("Render
 * tonight", specs/09-local-setup.md). A null followPoint lets the worker pick the subject.
 */
public record RenderSettings(
    String ratio,
    String quality,
    int fps,
    String style,
    String mode,
    Integer lengthSec,
    String prompt,
    boolean coolMode,
    long seed,
    Instant startAt,
    FollowPoint followPoint) {

  public static final String DEFAULT_RATIO = "9:16";
  public static final String DEFAULT_QUALITY = "4K";
  public static final int DEFAULT_FPS = 30;
  public static final String DEFAULT_STYLE = "auto";
  public static final String DEFAULT_MODE = "fast";

  private static final Set<String> RATIOS = Set.of("16:9", "9:16", "1:1", "4:5", "4:3", "21:9");
  private static final Set<String> QUALITIES = Set.of("4K", "6K", "8K");
  private static final Set<Integer> FRAME_RATES = Set.of(24, 30, 60);
  private static final Set<String> MODES = Set.of("preview", "fast", "max");

  /**
   * Where the user tapped to pick the subject to follow. x and y run 0 to 1 across the frame,
   * timeSec is the moment of the clip being previewed, assetId the 360 clip it was tapped on (null
   * means the first 360 clip). Spec: specs/08-osmo360.md#ui-additions
   */
  public record FollowPoint(double x, double y, double timeSec, UUID assetId) {
    public FollowPoint {
      if (x < 0 || x > 1 || y < 0 || y > 1) {
        throw new IllegalArgumentException("followPoint x and y must be between 0 and 1");
      }
      if (timeSec < 0) {
        throw new IllegalArgumentException("followPoint timeSec must not be negative");
      }
    }
  }

  public RenderSettings {
    requireOneOf("ratio", ratio, RATIOS);
    requireOneOf("quality", quality, QUALITIES);
    requireOneOf("fps", fps, FRAME_RATES);
    requireOneOf("mode", mode, MODES);
    Objects.requireNonNull(style, "style");
    if (lengthSec != null && lengthSec <= 0) {
      throw new IllegalArgumentException("lengthSec must be positive");
    }
  }

  public RenderSettings withSeed(long newSeed) {
    return new RenderSettings(
        ratio,
        quality,
        fps,
        style,
        mode,
        lengthSec,
        prompt,
        coolMode,
        newSeed,
        startAt,
        followPoint);
  }

  /** The same settings with no start time, for a version that should run right away. */
  public RenderSettings withoutStartTime() {
    return new RenderSettings(
        ratio, quality, fps, style, mode, lengthSec, prompt, coolMode, seed, null, followPoint);
  }

  private static <T> void requireOneOf(String name, T value, Set<T> allowed) {
    if (value == null || !allowed.contains(value)) {
      throw new IllegalArgumentException(name + " must be one of " + allowed);
    }
  }
}
