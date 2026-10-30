package com.editographer.asset.domain;

import com.editographer.project.domain.ProjectId;
import com.editographer.storage.domain.MediaPath;
import java.time.Instant;
import java.util.Objects;

/**
 * An uploaded file and what analysis has learned about it. Fields the worker fills in stay null
 * until analysis finishes. Spec: specs/07-api-and-data.md#database-h2-file-mode-flyway-migrations
 */
public record Asset(
    AssetId id,
    ProjectId projectId,
    AssetType type,
    String filename,
    MediaPath path,
    long sizeBytes,
    AnalysisStatus analysisStatus,
    String fileHash,
    Double durationSec,
    Integer width,
    Integer height,
    Double fps,
    String cameraMode,
    String logProfile,
    String analysisPath,
    Instant createdAt) {

  private static final String UPLOADS_FOLDER = "uploads";

  public Asset {
    Objects.requireNonNull(id, "id");
    Objects.requireNonNull(projectId, "projectId");
    Objects.requireNonNull(type, "type");
    Objects.requireNonNull(filename, "filename");
    Objects.requireNonNull(path, "path");
    Objects.requireNonNull(analysisStatus, "analysisStatus");
    Objects.requireNonNull(createdAt, "createdAt");
    if (filename.isBlank()) {
      throw new IllegalArgumentException("Asset filename must not be blank");
    }
    if (sizeBytes < 0) {
      throw new IllegalArgumentException("Asset size must not be negative");
    }
  }

  /** A newly uploaded file, stored as uploads/{projectId}/{assetId}.{ext}, awaiting analysis. */
  public static Asset uploaded(
      ProjectId projectId, AssetType type, String filename, long sizeBytes, Instant now) {
    AssetId id = AssetId.newId();
    return new Asset(
        id,
        projectId,
        type,
        filename,
        storagePath(projectId, id, filename),
        sizeBytes,
        AnalysisStatus.PENDING,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        now);
  }

  public Asset withAnalysisStatus(AnalysisStatus status) {
    return new Asset(
        id,
        projectId,
        type,
        filename,
        path,
        sizeBytes,
        status,
        fileHash,
        durationSec,
        width,
        height,
        fps,
        cameraMode,
        logProfile,
        analysisPath,
        createdAt);
  }

  /** The asset once the worker has finished analyzing it. */
  public Asset withAnalysis(AnalysisResult result) {
    return new Asset(
        id,
        projectId,
        type,
        filename,
        path,
        sizeBytes,
        AnalysisStatus.DONE,
        result.fileHash(),
        result.durationSec(),
        result.width(),
        result.height(),
        result.fps(),
        result.cameraMode(),
        result.logProfile(),
        result.analysisPath(),
        createdAt);
  }

  /** The folder that holds every upload of a project. */
  public static MediaPath projectFolder(ProjectId projectId) {
    return new MediaPath(UPLOADS_FOLDER + "/" + projectId.value());
  }

  private static MediaPath storagePath(ProjectId projectId, AssetId id, String filename) {
    String name = id.value() + "." + AssetType.extensionOf(filename);
    return new MediaPath(projectFolder(projectId).value() + "/" + name);
  }
}
