package com.editographer.project.application;

import com.editographer.asset.domain.Asset;
import com.editographer.asset.domain.AssetRepository;
import com.editographer.common.error.ApiException;
import com.editographer.common.error.ErrorCode;
import com.editographer.project.domain.Project;
import com.editographer.project.domain.ProjectId;
import com.editographer.project.domain.ProjectRepository;
import com.editographer.render.domain.Render;
import com.editographer.render.domain.RenderRepository;
import com.editographer.storage.domain.MediaPath;
import com.editographer.storage.domain.MediaWriter;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.time.Clock;
import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Project use cases. Spec: specs/07-api-and-data.md#backend-rest-api-spring-boot-port-8080 */
@Service
public class ProjectService {

  private final ProjectRepository projects;
  private final AssetRepository assets;
  private final RenderRepository renders;
  private final MediaWriter mediaWriter;
  private final Clock clock;

  public ProjectService(
      ProjectRepository projects,
      AssetRepository assets,
      RenderRepository renders,
      MediaWriter mediaWriter,
      Clock clock) {
    this.projects = projects;
    this.assets = assets;
    this.renders = renders;
    this.mediaWriter = mediaWriter;
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
    List<MediaPath> folders = new ArrayList<>();
    folders.add(Asset.projectFolder(id));
    assets.findByProject(id).forEach(asset -> folders.add(asset.workerProxyPath()));
    renders.findByProject(id).forEach(render -> folders.add(Render.folder(render.id())));
    projects.deleteById(id);
    try {
      for (MediaPath folder : folders) {
        mediaWriter.delete(folder);
      }
    } catch (IOException exception) {
      throw new UncheckedIOException("Could not delete media of project " + id.value(), exception);
    }
  }

  private static ApiException notFound(ProjectId id) {
    return new ApiException(ErrorCode.PROJECT_NOT_FOUND, "Project " + id.value() + " not found");
  }
}
