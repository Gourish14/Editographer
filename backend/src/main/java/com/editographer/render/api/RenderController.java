package com.editographer.render.api;

import com.editographer.common.error.ApiException;
import com.editographer.common.error.ErrorCode;
import com.editographer.events.application.EventStreams;
import com.editographer.project.domain.ProjectId;
import com.editographer.render.api.dto.CreateRenderRequest;
import com.editographer.render.api.dto.RenderResponse;
import com.editographer.render.application.RenderService;
import com.editographer.render.domain.RenderId;
import com.editographer.storage.domain.MediaLocator;
import com.editographer.storage.domain.MediaPath;
import jakarta.validation.Valid;
import java.net.URI;
import java.util.UUID;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * REST endpoints for renders. Returning a Resource gives Range support, which video seeking needs.
 * Spec: specs/07-api-and-data.md
 */
@RestController
public final class RenderController {

  private static final MediaType VIDEO_MP4 = MediaType.parseMediaType("video/mp4");

  private final RenderService service;
  private final EventStreams streams;
  private final MediaLocator mediaLocator;

  public RenderController(RenderService service, EventStreams streams, MediaLocator mediaLocator) {
    this.service = service;
    this.streams = streams;
    this.mediaLocator = mediaLocator;
  }

  @PostMapping("/api/projects/{id}/renders")
  public ResponseEntity<RenderResponse> start(
      @PathVariable("id") UUID projectId, @Valid @RequestBody CreateRenderRequest request) {
    return created(
        RenderResponse.from(
            service.startRender(
                new ProjectId(projectId), request.toSettings(RenderService.randomSeed()))));
  }

  @GetMapping("/api/renders/{id}")
  public RenderResponse get(@PathVariable("id") UUID id) {
    return RenderResponse.from(service.getRender(new RenderId(id)));
  }

  @GetMapping(path = "/api/renders/{id}/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
  public SseEmitter events(@PathVariable("id") UUID id) {
    return streams.open(id, service.currentEvent(new RenderId(id)));
  }

  @PostMapping("/api/renders/{id}/regenerate")
  public ResponseEntity<RenderResponse> regenerate(@PathVariable("id") UUID id) {
    return created(RenderResponse.from(service.regenerate(new RenderId(id))));
  }

  @PostMapping("/api/renders/{id}/cancel")
  public RenderResponse cancel(@PathVariable("id") UUID id) {
    return RenderResponse.from(service.cancel(new RenderId(id)));
  }

  @GetMapping("/api/renders/{id}/preview")
  public ResponseEntity<Resource> preview(@PathVariable("id") UUID id) {
    return ResponseEntity.ok()
        .contentType(VIDEO_MP4)
        .body(video(service.previewOf(new RenderId(id))));
  }

  @GetMapping("/api/renders/{id}/download")
  public ResponseEntity<Resource> download(@PathVariable("id") UUID id) {
    String disposition =
        ContentDisposition.attachment().filename("editographer-" + id + ".mp4").build().toString();
    return ResponseEntity.ok()
        .contentType(VIDEO_MP4)
        .header(HttpHeaders.CONTENT_DISPOSITION, disposition)
        .body(video(service.outputOf(new RenderId(id))));
  }

  private Resource video(MediaPath path) {
    if (!mediaLocator.exists(path)) {
      throw new ApiException(ErrorCode.RENDER_NOT_READY, "The video file is missing");
    }
    return new FileSystemResource(mediaLocator.locate(path));
  }

  private static ResponseEntity<RenderResponse> created(RenderResponse render) {
    return ResponseEntity.created(URI.create("/api/renders/" + render.id())).body(render);
  }
}
