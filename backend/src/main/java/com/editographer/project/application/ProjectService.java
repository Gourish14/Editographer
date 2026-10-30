package com.editographer.project.application;

import com.editographer.common.error.ApiException;
import com.editographer.common.error.ErrorCode;
import com.editographer.project.domain.Project;
import com.editographer.project.domain.ProjectId;
import com.editographer.project.domain.ProjectRepository;
import java.time.Clock;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Project use cases. Spec: specs/07-api-and-data.md#backend-rest-api-spring-boot-port-8080 */
@Service
public class ProjectService {

  private final ProjectRepository projects;
  private final Clock clock;

  public ProjectService(ProjectRepository projects, Clock clock) {
    this.projects = projects;
    this.clock = clock;
  }

  @Transactional
  public Project createProject(String name) {
    return projects.save(Project.create(name, clock.instant()));
  }

  @Transactional(readOnly = true)
  public List<Project> listProjects() {
    return projects.findAll();
  }

  @Transactional(readOnly = true)
  public Project getProject(ProjectId id) {
    return projects.findById(id).orElseThrow(() -> notFound(id));
  }

  @Transactional
  public void deleteProject(ProjectId id) {
    if (!projects.existsById(id)) {
      throw notFound(id);
    }
    projects.deleteById(id);
  }

  private static ApiException notFound(ProjectId id) {
    return new ApiException(ErrorCode.PROJECT_NOT_FOUND, "Project " + id.value() + " not found");
  }
}
