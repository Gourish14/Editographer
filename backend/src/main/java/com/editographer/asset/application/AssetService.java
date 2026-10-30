package com.editographer.asset.application;

import com.editographer.asset.domain.Asset;
import com.editographer.asset.domain.AssetId;
import com.editographer.asset.domain.AssetRepository;
import com.editographer.common.error.ApiException;
import com.editographer.common.error.ErrorCode;
import com.editographer.project.domain.ProjectId;
import com.editographer.project.domain.ProjectRepository;
import com.editographer.storage.domain.MediaLocator;
import com.editographer.storage.domain.MediaPath;
import com.editographer.storage.domain.MediaWriter;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Asset use cases. Spec: specs/07-api-and-data.md#backend-rest-api-spring-boot-port-8080 */
@Service
public class AssetService {

  private static final String THUMBNAIL_FILE = "thumbnail.jpg";

  private final AssetRepository assets;
  private final ProjectRepository projects;
  private final MediaLocator mediaLocator;
  private final MediaWriter mediaWriter;

  public AssetService(
      AssetRepository assets,
      ProjectRepository projects,
      MediaLocator mediaLocator,
      MediaWriter mediaWriter) {
    this.assets = assets;
    this.projects = projects;
    this.mediaLocator = mediaLocator;
    this.mediaWriter = mediaWriter;
  }

  @Transactional(readOnly = true)
  public List<Asset> listAssets(ProjectId projectId) {
    if (!projects.existsById(projectId)) {
      throw new ApiException(
          ErrorCode.PROJECT_NOT_FOUND, "Project " + projectId.value() + " not found");
    }
    return assets.findByProject(projectId);
  }

  /** Where the worker put the asset's thumbnail. Fails until analysis has produced one. */
  @Transactional(readOnly = true)
  public MediaPath thumbnailOf(AssetId id) {
    Asset asset = find(id);
    if (asset.fileHash() != null) {
      MediaPath thumbnail = new MediaPath("cache/" + asset.fileHash() + "/" + THUMBNAIL_FILE);
      if (mediaLocator.exists(thumbnail)) {
        return thumbnail;
      }
    }
    throw new ApiException(
        ErrorCode.ASSET_NOT_FOUND, "Asset " + id.value() + " has no thumbnail yet");
  }

  @Transactional
  public void deleteAsset(AssetId id) {
    Asset asset = find(id);
    assets.deleteById(id);
    try {
      mediaWriter.delete(asset.path());
    } catch (IOException exception) {
      throw new UncheckedIOException("Could not delete the file of asset " + id.value(), exception);
    }
  }

  private Asset find(AssetId id) {
    return assets
        .findById(id)
        .orElseThrow(
            () ->
                new ApiException(ErrorCode.ASSET_NOT_FOUND, "Asset " + id.value() + " not found"));
  }
}
