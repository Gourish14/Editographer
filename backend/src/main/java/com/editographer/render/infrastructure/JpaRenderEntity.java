package com.editographer.render.infrastructure;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Lob;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

/** JPA row for a render. Never leaves the infrastructure layer. */
@Entity
@Table(name = "render_job")
class JpaRenderEntity {

  @Id UUID id;

  @Column(name = "project_id", nullable = false)
  UUID projectId;

  @Column(nullable = false)
  String ratio;

  @Column(nullable = false)
  String quality;

  @Column(nullable = false)
  int fps;

  @Column(nullable = false)
  String style;

  @Column(nullable = false)
  String mode;

  @Column(name = "length_sec")
  Integer lengthSec;

  @Lob String prompt;

  @Column(name = "cool_mode", nullable = false)
  boolean coolMode;

  @Column(nullable = false)
  long seed;

  @Column(name = "start_at")
  Instant startAt;

  @Column(name = "follow_x")
  Double followX;

  @Column(name = "follow_y")
  Double followY;

  @Column(name = "follow_time_sec")
  Double followTimeSec;

  @Column(name = "follow_asset_id")
  UUID followAssetId;

  @Column(nullable = false)
  String status;

  String stage;

  @Column(nullable = false)
  int progress;

  @Lob String log;

  @Lob
  @Column(name = "edit_plan")
  String editPlan;

  @Column(name = "preview_path")
  String previewPath;

  @Column(name = "output_path")
  String outputPath;

  String error;

  @Column(name = "created_at", nullable = false)
  Instant createdAt;

  @Column(name = "finished_at")
  Instant finishedAt;

  protected JpaRenderEntity() {}
}
