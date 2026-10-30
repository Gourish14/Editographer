package com.editographer.project.domain;

import java.util.List;
import java.util.Optional;

/** Port for storing projects. */
public interface ProjectRepository {

  Project save(Project project);

  /** All projects, newest first. */
  List<Project> findAll();

  Optional<Project> findById(ProjectId id);

  boolean existsById(ProjectId id);

  void deleteById(ProjectId id);
}
