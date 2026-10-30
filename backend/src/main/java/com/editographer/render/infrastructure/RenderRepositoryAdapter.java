package com.editographer.render.infrastructure;

import com.editographer.project.domain.ProjectId;
import com.editographer.render.domain.Render;
import com.editographer.render.domain.RenderId;
import com.editographer.render.domain.RenderRepository;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Component;

/** JPA implementation of the render port. */
@Component
final class RenderRepositoryAdapter implements RenderRepository {

  private final JpaRenderRepository jpa;

  RenderRepositoryAdapter(JpaRenderRepository jpa) {
    this.jpa = jpa;
  }

  @Override
  public Render save(Render render) {
    return RenderMapper.toDomain(jpa.save(RenderMapper.toEntity(render)));
  }

  @Override
  public Optional<Render> findById(RenderId id) {
    return jpa.findById(id.value()).map(RenderMapper::toDomain);
  }

  @Override
  public List<Render> findByProject(ProjectId projectId) {
    return jpa.findByProjectIdOrderByCreatedAtDesc(projectId.value()).stream()
        .map(RenderMapper::toDomain)
        .toList();
  }
}
