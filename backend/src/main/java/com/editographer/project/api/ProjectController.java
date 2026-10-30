package com.editographer.project.api;

import com.editographer.asset.api.dto.AssetResponse;
import com.editographer.asset.application.AssetService;
import com.editographer.project.api.dto.CreateProjectRequest;
import com.editographer.project.api.dto.ProjectDetailResponse;
import com.editographer.project.api.dto.ProjectResponse;
import com.editographer.project.application.ProjectService;
import com.editographer.project.domain.ProjectId;
import jakarta.validation.Valid;
import java.net.URI;
import java.util.List;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/** REST endpoints for projects. Spec: specs/07-api-and-data.md */
@RestController
@RequestMapping(ProjectController.BASE_PATH)
public final class ProjectController {

  static final String BASE_PATH = "/api/projects";

  private final ProjectService service;
  private final AssetService assets;

  public ProjectController(ProjectService service, AssetService assets) {
    this.service = service;
    this.assets = assets;
  }

  @GetMapping
  public List<ProjectResponse> list() {
    return service.listProjects().stream().map(ProjectResponse::from).toList();
  }

  @PostMapping
  public ResponseEntity<ProjectResponse> create(@Valid @RequestBody CreateProjectRequest request) {
    ProjectResponse created = ProjectResponse.from(service.createProject(request.name()));
    return ResponseEntity.created(URI.create(BASE_PATH + "/" + created.id())).body(created);
  }

  @GetMapping("/{id}")
  public ProjectDetailResponse get(@PathVariable("id") UUID id) {
    ProjectId projectId = new ProjectId(id);
    return new ProjectDetailResponse(
        ProjectResponse.from(service.getProject(projectId)),
        assets.listAssets(projectId).stream().map(AssetResponse::from).toList());
  }

  @DeleteMapping("/{id}")
  @ResponseStatus(HttpStatus.NO_CONTENT)
  public void delete(@PathVariable("id") UUID id) {
    service.deleteProject(new ProjectId(id));
  }
}
