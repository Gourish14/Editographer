package com.editographer.project.domain;

import java.time.Instant;
import java.util.Objects;

/** A named collection of assets and renders. Spec: specs/07-api-and-data.md */
public record Project(ProjectId id, String name, Instant createdAt) {

  public static final int MAX_NAME_LENGTH = 255;

  public Project {
    Objects.requireNonNull(id, "id");
    Objects.requireNonNull(name, "name");
    Objects.requireNonNull(createdAt, "createdAt");
    if (name.isBlank()) {
      throw new IllegalArgumentException("Project name must not be blank");
    }
    if (name.length() > MAX_NAME_LENGTH) {
      throw new IllegalArgumentException(
          "Project name must be at most " + MAX_NAME_LENGTH + " characters");
    }
  }

  public static Project create(String name, Instant now) {
    return new Project(ProjectId.newId(), name.strip(), now);
  }
}
