package com.editographer.render.infrastructure;

import com.editographer.project.domain.ProjectId;
import com.editographer.render.domain.Render;
import com.editographer.render.domain.RenderId;
import com.editographer.render.domain.RenderSettings;
import com.editographer.render.domain.RenderState;
import com.editographer.render.domain.RenderStatus;
import com.editographer.storage.domain.MediaPath;

/** Converts between the domain model and its JPA row. */
final class RenderMapper {

  private RenderMapper() {}

  static JpaRenderEntity toEntity(Render render) {
    RenderSettings settings = render.settings();
    RenderState state = render.state();
    JpaRenderEntity entity = new JpaRenderEntity();
    entity.id = render.id().value();
    entity.projectId = render.projectId().value();
    entity.ratio = settings.ratio();
    entity.quality = settings.quality();
    entity.fps = settings.fps();
    entity.style = settings.style();
    entity.mode = settings.mode();
    entity.lengthSec = settings.lengthSec();
    entity.prompt = settings.prompt();
    entity.coolMode = settings.coolMode();
    entity.seed = settings.seed();
    entity.startAt = settings.startAt();
    RenderSettings.FollowPoint follow = settings.followPoint();
    entity.followX = follow == null ? null : follow.x();
    entity.followY = follow == null ? null : follow.y();
    entity.followTimeSec = follow == null ? null : follow.timeSec();
    entity.status = state.status().name();
    entity.stage = state.stage();
    entity.progress = state.progress();
    entity.log = state.log();
    entity.editPlan = state.editPlan();
    entity.previewPath = pathValue(state.previewPath());
    entity.outputPath = pathValue(state.outputPath());
    entity.error = state.error();
    entity.createdAt = render.createdAt();
    entity.finishedAt = state.finishedAt();
    return entity;
  }

  static Render toDomain(JpaRenderEntity entity) {
    return new Render(
        new RenderId(entity.id),
        new ProjectId(entity.projectId),
        new RenderSettings(
            entity.ratio,
            entity.quality,
            entity.fps,
            entity.style,
            entity.mode,
            entity.lengthSec,
            entity.prompt,
            entity.coolMode,
            entity.seed,
            entity.startAt,
            entity.followX == null
                ? null
                : new RenderSettings.FollowPoint(
                    entity.followX, entity.followY, entity.followTimeSec)),
        new RenderState(
            RenderStatus.valueOf(entity.status),
            entity.stage,
            entity.progress,
            entity.log,
            entity.editPlan,
            mediaPath(entity.previewPath),
            mediaPath(entity.outputPath),
            entity.error,
            entity.finishedAt),
        entity.createdAt);
  }

  private static String pathValue(MediaPath path) {
    return path == null ? null : path.value();
  }

  private static MediaPath mediaPath(String value) {
    return value == null ? null : new MediaPath(value);
  }
}
