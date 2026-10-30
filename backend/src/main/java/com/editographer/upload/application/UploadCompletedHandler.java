package com.editographer.upload.application;

import com.editographer.asset.domain.AnalysisStatus;
import com.editographer.asset.domain.Asset;
import com.editographer.asset.domain.AssetRepository;
import com.editographer.asset.domain.AssetType;
import com.editographer.common.error.ApiException;
import com.editographer.common.error.ErrorCode;
import com.editographer.job.domain.JobKind;
import com.editographer.job.domain.JobQueue;
import com.editographer.project.domain.ProjectId;
import com.editographer.project.domain.ProjectRepository;
import com.editographer.storage.domain.MediaWriter;
import com.editographer.upload.domain.UploadMetadata;
import java.io.IOException;
import java.time.Clock;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Turns finished uploads into assets and queues their analysis. Spec:
 * specs/07-api-and-data.md#job-flow step 1
 */
@Service
public class UploadCompletedHandler {

  private final ProjectRepository projects;
  private final AssetRepository assets;
  private final MediaWriter mediaWriter;
  private final JobQueue jobQueue;
  private final Clock clock;

  public UploadCompletedHandler(
      ProjectRepository projects,
      AssetRepository assets,
      MediaWriter mediaWriter,
      JobQueue jobQueue,
      Clock clock) {
    this.projects = projects;
    this.assets = assets;
    this.mediaWriter = mediaWriter;
    this.jobQueue = jobQueue;
    this.clock = clock;
  }

  /** Refuses a bad upload before any bytes are sent. */
  @Transactional(readOnly = true)
  public void checkCanStart(String metadataHeader) {
    UploadMetadata metadata =
        UploadMetadata.parse(metadataHeader)
            .orElseThrow(
                () ->
                    new ApiException(
                        ErrorCode.UPLOAD_FAILED,
                        "Upload-Metadata must contain projectId and filename"));
    typeOf(metadata.filename());
    ProjectId projectId = new ProjectId(metadata.projectId());
    if (!projects.existsById(projectId)) {
      throw new ApiException(
          ErrorCode.PROJECT_NOT_FOUND, "Project " + projectId.value() + " not found");
    }
  }

  /** The file moves last, so any earlier failure leaves nothing behind in media/. */
  @Transactional
  public Asset complete(CompletedUpload upload) throws IOException {
    UploadMetadata metadata = upload.metadata();
    Asset asset =
        Asset.uploaded(
            new ProjectId(metadata.projectId()),
            typeOf(metadata.filename()),
            metadata.filename(),
            upload.sizeBytes(),
            clock.instant());
    if (asset.isCameraProxy()) {
      assets.save(asset.withAnalysisStatus(AnalysisStatus.DONE));
    } else {
      assets.save(asset);
      jobQueue.enqueue(JobKind.ANALYZE, asset.id().value());
    }
    mediaWriter.moveIn(upload.file(), asset.path());
    return asset;
  }

  private static AssetType typeOf(String filename) {
    return AssetType.fromFilename(filename)
        .orElseThrow(
            () ->
                new ApiException(
                    ErrorCode.ASSET_UNSUPPORTED, "Unsupported file type: " + filename));
  }
}
