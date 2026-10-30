package com.editographer.asset.infrastructure;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

/** JPA row for an asset. Never leaves the infrastructure layer. */
@Entity
@Table(name = "asset")
class JpaAssetEntity {

  @Id private UUID id;

  @Column(name = "project_id", nullable = false)
  private UUID projectId;

  @Column(nullable = false)
  private String type;

  @Column(nullable = false)
  private String filename;

  @Column(nullable = false)
  private String path;

  @Column(name = "size_bytes", nullable = false)
  private long sizeBytes;

  @Column(name = "analysis_status", nullable = false)
  private String analysisStatus;

  @Column(name = "file_hash")
  private String fileHash;

  @Column(name = "duration_sec")
  private Double durationSec;

  private Integer width;

  private Integer height;

  private Double fps;

  @Column(name = "camera_mode")
  private String cameraMode;

  @Column(name = "log_profile")
  private String logProfile;

  @Column(name = "analysis_path")
  private String analysisPath;

  @Column(name = "created_at", nullable = false)
  private Instant createdAt;

  protected JpaAssetEntity() {}

  JpaAssetEntity(
      UUID id,
      UUID projectId,
      String type,
      String filename,
      String path,
      long sizeBytes,
      String analysisStatus,
      String fileHash,
      Double durationSec,
      Integer width,
      Integer height,
      Double fps,
      String cameraMode,
      String logProfile,
      String analysisPath,
      Instant createdAt) {
    this.id = id;
    this.projectId = projectId;
    this.type = type;
    this.filename = filename;
    this.path = path;
    this.sizeBytes = sizeBytes;
    this.analysisStatus = analysisStatus;
    this.fileHash = fileHash;
    this.durationSec = durationSec;
    this.width = width;
    this.height = height;
    this.fps = fps;
    this.cameraMode = cameraMode;
    this.logProfile = logProfile;
    this.analysisPath = analysisPath;
    this.createdAt = createdAt;
  }

  UUID getId() {
    return id;
  }

  UUID getProjectId() {
    return projectId;
  }

  String getType() {
    return type;
  }

  String getFilename() {
    return filename;
  }

  String getPath() {
    return path;
  }

  long getSizeBytes() {
    return sizeBytes;
  }

  String getAnalysisStatus() {
    return analysisStatus;
  }

  String getFileHash() {
    return fileHash;
  }

  Double getDurationSec() {
    return durationSec;
  }

  Integer getWidth() {
    return width;
  }

  Integer getHeight() {
    return height;
  }

  Double getFps() {
    return fps;
  }

  String getCameraMode() {
    return cameraMode;
  }

  String getLogProfile() {
    return logProfile;
  }

  String getAnalysisPath() {
    return analysisPath;
  }

  Instant getCreatedAt() {
    return createdAt;
  }
}
