package com.editographer.upload.application;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.Optional;

/** Port for the resumable upload protocol. Spec: specs/02-architecture.md#communication */
public interface ResumableUploads {

  /** Handles one protocol request. Returns the upload when this request finished it. */
  Optional<CompletedUpload> handle(HttpServletRequest request, HttpServletResponse response)
      throws IOException;

  /** Forgets a finished upload once its file has been moved out. */
  void release(CompletedUpload upload) throws IOException;
}
