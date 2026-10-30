package com.editographer.render.domain;

import java.util.Objects;
import java.util.Set;

/**
 * What the user chose for a render. A null lengthSec means Auto. Spec:
 * specs/00-overview.md#user-choices
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
    long seed) {

  public static final String DEFAULT_RATIO = "9:16";
  public static final String DEFAULT_QUALITY = "4K";
  public static final int DEFAULT_FPS = 30;
  public static final String DEFAULT_STYLE = "auto";
  public static final String DEFAULT_MODE = "fast";

  private static final Set<String> RATIOS = Set.of("16:9", "9:16", "1:1", "4:5", "4:3", "21:9");
  private static final Set<String> QUALITIES = Set.of("4K", "6K", "8K");
  private static final Set<Integer> FRAME_RATES = Set.of(24, 30, 60);
  private static final Set<String> MODES = Set.of("preview", "fast", "max");

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
        ratio, quality, fps, style, mode, lengthSec, prompt, coolMode, newSeed);
  }

  private static <T> void requireOneOf(String name, T value, Set<T> allowed) {
    if (value == null || !allowed.contains(value)) {
      throw new IllegalArgumentException(name + " must be one of " + allowed);
    }
  }
}
