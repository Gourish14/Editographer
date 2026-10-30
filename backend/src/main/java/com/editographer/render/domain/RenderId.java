package com.editographer.render.domain;

import java.util.Objects;
import java.util.UUID;

/** Identity of a render. */
public record RenderId(UUID value) {

  public RenderId {
    Objects.requireNonNull(value, "value");
  }

  public static RenderId newId() {
    return new RenderId(UUID.randomUUID());
  }
}
