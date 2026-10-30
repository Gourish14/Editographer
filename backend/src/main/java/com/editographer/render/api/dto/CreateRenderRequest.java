package com.editographer.render.api.dto;

import com.editographer.common.error.ApiException;
import com.editographer.common.error.ErrorCode;
import com.editographer.render.domain.RenderSettings;

/**
 * Body of POST /api/projects/{id}/renders. Anything left out takes the default from
 * specs/00-overview.md#user-choices.
 */
public record CreateRenderRequest(
    String ratio,
    String quality,
    Integer fps,
    String style,
    String mode,
    Integer lengthSec,
    String prompt,
    Boolean coolMode,
    Long seed) {

  /** The settings to render with, using randomSeed when the request names no seed. */
  public RenderSettings toSettings(long randomSeed) {
    try {
      return new RenderSettings(
          orDefault(ratio, RenderSettings.DEFAULT_RATIO),
          orDefault(quality, RenderSettings.DEFAULT_QUALITY),
          orDefault(fps, RenderSettings.DEFAULT_FPS),
          orDefault(style, RenderSettings.DEFAULT_STYLE),
          orDefault(mode, RenderSettings.DEFAULT_MODE),
          lengthSec,
          prompt,
          orDefault(coolMode, Boolean.FALSE),
          orDefault(seed, randomSeed));
    } catch (IllegalArgumentException exception) {
      throw new ApiException(ErrorCode.VALIDATION_FAILED, exception.getMessage(), exception);
    }
  }

  private static <T> T orDefault(T value, T fallback) {
    return value != null ? value : fallback;
  }
}
