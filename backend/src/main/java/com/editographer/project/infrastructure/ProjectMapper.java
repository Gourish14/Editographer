package com.editographer.project.infrastructure;

import com.editographer.project.domain.Project;
import com.editographer.project.domain.ProjectId;

/** Converts between the domain model and its JPA row. */
final class ProjectMapper {

  private ProjectMapper() {}

  static JpaProjectEntity toEntity(Project project) {
    return new JpaProjectEntity(project.id().value(), project.name(), project.createdAt());
  }

  static Project toDomain(JpaProjectEntity entity) {
    return new Project(new ProjectId(entity.getId()), entity.getName(), entity.getCreatedAt());
  }
}
