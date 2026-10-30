package com.editographer.project.api.dto;

import com.editographer.project.domain.Project;
import java.time.Instant;
import java.util.UUID;

/** A project as seen by API clients. */
public record ProjectResponse(UUID id, String name, Instant createdAt) {

  public static ProjectResponse from(Project project) {
    return new ProjectResponse(project.id().value(), project.name(), project.createdAt());
  }
}
