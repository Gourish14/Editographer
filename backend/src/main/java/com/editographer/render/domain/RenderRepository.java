package com.editographer.render.domain;

import com.editographer.project.domain.ProjectId;
import java.util.List;
import java.util.Optional;

/** Port for storing renders. */
public interface RenderRepository {

  Render save(Render render);

  Optional<Render> findById(RenderId id);

  /** A project's renders, newest first. */
  List<Render> findByProject(ProjectId projectId);
}
