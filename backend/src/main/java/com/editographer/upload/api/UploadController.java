package com.editographer.upload.api;

import com.editographer.upload.application.CompletedUpload;
import com.editographer.upload.application.ResumableUploads;
import com.editographer.upload.application.UploadCompletedHandler;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.Optional;
import org.springframework.http.HttpMethod;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RestController;

/** Entry point for tus uploads. Spec: specs/07-api-and-data.md#backend-rest-api */
@RestController
public final class UploadController {

  private static final String METADATA_HEADER = "Upload-Metadata";

  private final ResumableUploads uploads;
  private final UploadCompletedHandler handler;

  public UploadController(ResumableUploads uploads, UploadCompletedHandler handler) {
    this.uploads = uploads;
    this.handler = handler;
  }

  @RequestMapping(
      value = {"/api/uploads", "/api/uploads/**"},
      method = {
        RequestMethod.POST,
        RequestMethod.PATCH,
        RequestMethod.HEAD,
        RequestMethod.DELETE,
        RequestMethod.OPTIONS
      })
  public void upload(HttpServletRequest request, HttpServletResponse response) throws IOException {
    if (HttpMethod.POST.matches(request.getMethod())) {
      handler.checkCanStart(request.getHeader(METADATA_HEADER));
    }
    Optional<CompletedUpload> completed = uploads.handle(request, response);
    if (completed.isPresent()) {
      handler.complete(completed.get());
      uploads.release(completed.get());
    }
  }
}
