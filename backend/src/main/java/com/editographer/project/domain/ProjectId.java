package com.editographer.project.domain;

import java.util.Objects;
import java.util.UUID;

/** Identity of a project. */
public record ProjectId(UUID value) {

  public ProjectId {
    Objects.requireNonNull(value, "value");
  }

  public static ProjectId newId() {
    return new ProjectId(UUID.randomUUID());
  }
}
