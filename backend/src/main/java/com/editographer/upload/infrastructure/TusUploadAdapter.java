package com.editographer.upload.infrastructure;

import com.editographer.common.error.ApiException;
import com.editographer.common.error.ErrorCode;
import com.editographer.upload.application.CompletedUpload;
import com.editographer.upload.application.ResumableUploads;
import com.editographer.upload.domain.UploadMetadata;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Optional;
import me.desair.tus.server.TusFileUploadService;
import me.desair.tus.server.exception.TusException;
import me.desair.tus.server.upload.UploadInfo;

/**
 * tus protocol through tus-java-server. A finished 16 GB file is renamed out of the library's
 * folder rather than copied. Spec: specs/02-architecture.md#communication
 */
final class TusUploadAdapter implements ResumableUploads {

  private static final String UPLOADS_SUBFOLDER = "uploads";
  private static final String DATA_FILE = "data";

  private final TusFileUploadService tus;
  private final Path storageFolder;

  TusUploadAdapter(TusFileUploadService tus, Path storageFolder) {
    this.tus = tus;
    this.storageFolder = storageFolder;
  }

  @Override
  public Optional<CompletedUpload> handle(HttpServletRequest request, HttpServletResponse response)
      throws IOException {
    tus.process(request, response);
    if (!"PATCH".equals(request.getMethod())) {
      return Optional.empty();
    }
    String uri = request.getRequestURI();
    try {
      UploadInfo info = tus.getUploadInfo(uri);
      if (info == null || info.isUploadInProgress()) {
        return Optional.empty();
      }
      return Optional.of(toCompleted(uri, info));
    } catch (TusException exception) {
      throw new ApiException(ErrorCode.UPLOAD_FAILED, "Could not read upload state", exception);
    }
  }

  @Override
  public void release(CompletedUpload upload) throws IOException {
    try {
      tus.deleteUpload(upload.uploadUri());
    } catch (TusException exception) {
      throw new IOException("Could not clean up a finished upload", exception);
    }
  }

  private CompletedUpload toCompleted(String uri, UploadInfo info)
      throws IOException, TusException {
    UploadMetadata metadata =
        UploadMetadata.parse(info.getEncodedMetadata())
            .orElseThrow(
                () -> new ApiException(ErrorCode.UPLOAD_FAILED, "Upload lost its metadata"));
    Path data =
        storageFolder
            .resolve(UPLOADS_SUBFOLDER)
            .resolve(info.getId().toString())
            .resolve(DATA_FILE);
    if (!Files.exists(data)) {
      data = copyOut(uri);
    }
    return new CompletedUpload(uri, metadata, data, info.getLength());
  }

  /** Fallback if the library ever changes its folder layout. */
  private Path copyOut(String uri) throws IOException, TusException {
    Path copy = Files.createTempFile(storageFolder, "upload", ".part");
    try (var bytes = tus.getUploadedBytes(uri)) {
      Files.copy(bytes, copy, StandardCopyOption.REPLACE_EXISTING);
    }
    return copy;
  }
}
