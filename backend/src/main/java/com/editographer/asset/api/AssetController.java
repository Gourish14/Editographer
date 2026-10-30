package com.editographer.asset.api;

import com.editographer.asset.api.dto.AssetResponse;
import com.editographer.asset.application.AssetService;
import com.editographer.asset.domain.AssetId;
import com.editographer.project.domain.ProjectId;
import com.editographer.storage.domain.MediaLocator;
import java.util.List;
import java.util.UUID;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/** REST endpoints for assets. Spec: specs/07-api-and-data.md */
@RestController
public final class AssetController {

  private final AssetService service;
  private final MediaLocator mediaLocator;

  public AssetController(AssetService service, MediaLocator mediaLocator) {
    this.service = service;
    this.mediaLocator = mediaLocator;
  }

  @GetMapping("/api/projects/{id}/assets")
  public List<AssetResponse> list(@PathVariable("id") UUID projectId) {
    return service.listAssets(new ProjectId(projectId)).stream().map(AssetResponse::from).toList();
  }

  @GetMapping("/api/assets/{id}/thumbnail")
  public ResponseEntity<Resource> thumbnail(@PathVariable("id") UUID id) {
    Resource image =
        new FileSystemResource(mediaLocator.locate(service.thumbnailOf(new AssetId(id))));
    return ResponseEntity.ok().contentType(MediaType.IMAGE_JPEG).body(image);
  }

  @GetMapping("/api/assets/{id}/waveform")
  public ResponseEntity<Resource> waveform(@PathVariable("id") UUID id) {
    Resource document =
        new FileSystemResource(mediaLocator.locate(service.waveformOf(new AssetId(id))));
    return ResponseEntity.ok().contentType(MediaType.APPLICATION_JSON).body(document);
  }

  @DeleteMapping("/api/assets/{id}")
  @ResponseStatus(HttpStatus.NO_CONTENT)
  public void delete(@PathVariable("id") UUID id) {
    service.deleteAsset(new AssetId(id));
  }
}
