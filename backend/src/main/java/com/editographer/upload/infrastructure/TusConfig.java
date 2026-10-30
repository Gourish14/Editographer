package com.editographer.upload.infrastructure;

import com.editographer.common.config.AppProperties;
import com.editographer.upload.application.ResumableUploads;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import me.desair.tus.server.TusFileUploadService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** Wires the tus server. In-progress uploads live in media/uploads/.tus until they finish. */
@Configuration
public class TusConfig {

  private static final String UPLOAD_URI = "/api/uploads";
  private static final String TUS_FOLDER = "uploads/.tus";

  @Bean
  public ResumableUploads resumableUploads(AppProperties properties) throws IOException {
    Path folder = properties.mediaDir().resolve(TUS_FOLDER).toAbsolutePath().normalize();
    Files.createDirectories(folder);
    TusFileUploadService tus =
        new TusFileUploadService().withStoragePath(folder.toString()).withUploadUri(UPLOAD_URI);
    return new TusUploadAdapter(tus, folder);
  }
}
