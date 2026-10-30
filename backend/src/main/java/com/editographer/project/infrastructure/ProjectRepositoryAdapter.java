package com.editographer.project.infrastructure;

import com.editographer.project.domain.Project;
import com.editographer.project.domain.ProjectId;
import com.editographer.project.domain.ProjectRepository;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Component;

/** JPA implementation of the project port. */
@Component
final class ProjectRepositoryAdapter implements ProjectRepository {

  private final JpaProjectRepository jpa;

  ProjectRepositoryAdapter(JpaProjectRepository jpa) {
    this.jpa = jpa;
  }

  @Override
  public Project save(Project project) {
    return ProjectMapper.toDomain(jpa.save(ProjectMapper.toEntity(project)));
  }

  @Override
  public List<Project> findAll() {
    return jpa.findAllByOrderByCreatedAtDesc().stream().map(ProjectMapper::toDomain).toList();
  }

  @Override
  public Optional<Project> findById(ProjectId id) {
    return jpa.findById(id.value()).map(ProjectMapper::toDomain);
  }

  @Override
  public boolean existsById(ProjectId id) {
    return jpa.existsById(id.value());
  }

  @Override
  public void deleteById(ProjectId id) {
    jpa.deleteById(id.value());
  }
}
