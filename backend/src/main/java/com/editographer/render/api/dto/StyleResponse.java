package com.editographer.render.api.dto;

import com.editographer.render.domain.StylePreset;
import com.fasterxml.jackson.annotation.JsonRawValue;

/** A style preset as seen by API clients. */
public record StyleResponse(String id, String name, @JsonRawValue String defaults) {

  public static StyleResponse from(StylePreset preset) {
    return new StyleResponse(preset.id(), preset.name(), preset.defaults());
  }
}
